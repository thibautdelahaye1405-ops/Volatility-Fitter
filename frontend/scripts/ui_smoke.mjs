// Headless-Edge UI smoke (npm run smoke:ui): builds nothing, drives the built
// bundle through the WORKBENCH SHELL (UI SHELL v2) and fails on any uncaught
// page error or ErrorBoundary fallback:
//   1. every lens of the activity bar (Graph · Forwards · Parametric · Local
//      Vol · Quality) on the auto-opened node tab, plus the Parametric
//      "Compare" sub-view;
//   2. the nodes pane → tab round trip (click a node row, a tab appears);
//   3. every top-bar menu (File · Universe · Help · View · Layout) and every
//      dialog (Options · Manage universe · Keyboard shortcuts · About · Quick open);
//   4. LIVE only — the workspace FILE round trip (wave 3, A1): File ▸ Save as…
//      downloads a volfit-workspace/1 bundle, File ▸ Open… reopens it through
//      the file chooser and the status bar names the workspace.
// Server: when the backend venv + a built bundle exist, a single-origin
// SYNTHETIC server (backend/smoke_server.py: dist + API on one port, throw-away
// DB) drives a LIVE shell; otherwise vite preview serves dist/ alone and the
// session falls back to the mock smile (live-only lenses show their offline
// cards; step 4 is skipped). Either way the smoke asserts the shell never
// white-screens. Screenshots land in .smoke/.
//
// Prereqs: `npm run build`, Microsoft Edge (+ ../.venv for the live server).
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4188; // off the dev/preview defaults so a running app never collides
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");

const LENSES = [
  { name: "Graph" },
  { name: "Forwards" },
  { name: "Parametric" },
  // Sub-view of the Parametric chart card (V3.2 model comparison): clicked
  // via its SegmentedControl button after the lens mounts.
  { name: "Parametric", subview: "Compare", slug: "compare" },
  // 3D IV surface with the pointer parked on it: the crosshair badge
  // (`T … · expiry · k … · σ …`) must render (wave 3, B2; live only).
  { name: "Parametric", subview: "Surface", slug: "surface-crosshair", hover: true },
  { name: "Local Vol" },
  { name: "Quality" },
];
const MENUS = ["File", "Universe", "Help", "View", "Layout"];
// Dialogs: opened from the top bar (Options) / activity bar (Manage universe) /
// Help menu (shortcuts) / brand (About). Each must render role="dialog".
const DIALOGS = [
  { name: "Options", open: (p) => clickHeader(p, "Options") },
  { name: "Manage universe", open: (p) => clickAria(p, "Manage universe") },
  { name: "Keyboard shortcuts", open: async (p) => { await clickHeader(p, "Help"); await clickText(p, "Keyboard shortcuts"); } },
  { name: "About VolFit", open: (p) => clickHeader(p, "About VolFit", "title") },
  // Ctrl+P quick-open palette (role=dialog "Quick open").
  { name: "Quick open", open: async (p) => { await p.keyboard.down("Control"); await p.keyboard.press("KeyP"); await p.keyboard.up("Control"); } },
  // Ctrl+K command palette (role=dialog "Command palette", ">" pre-filled;
  // wave 3, C4) — must list commands.
  { name: "Command palette", open: async (p) => {
    await p.keyboard.down("Control"); await p.keyboard.press("KeyK"); await p.keyboard.up("Control");
    await sleep(300);
    const n = await p.evaluate(() => document.querySelectorAll('[role="dialog"] [role="option"]').length);
    if (n < 10) throw new Error(`command palette lists ${n} commands`);
  } },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickHeader(page, label, attr = "text") {
  const sel = attr === "title"
    ? `xpath/.//header//button[@title="${label}"]`
    : `xpath/.//header//button[.//span[normalize-space()="${label}"] or normalize-space()="${label}"]`;
  const [btn] = await page.$$(sel);
  if (!btn) throw new Error(`header button "${label}" not found`);
  await btn.click();
  await sleep(200);
}
async function clickAria(page, label) {
  const btn = await page.$(`button[aria-label="${label}"]`);
  if (!btn) throw new Error(`button[aria-label="${label}"] not found`);
  await btn.click();
  await sleep(200);
}
async function clickText(page, label) {
  const [btn] = await page.$$(`xpath/.//span[normalize-space()="${label}"]/ancestor::button[1]`);
  if (!btn) throw new Error(`row "${label}" not found`);
  await btn.click();
  await sleep(200);
}

const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));

function startPreview() {
  // Spawn the vite JS bin through THIS node: no .cmd shim (Node >= 20 EINVALs
  // on .cmd spawns without a shell) and no PATH dependence.
  const viteBin = winPath(new URL("../node_modules/vite/bin/vite.js", import.meta.url));
  const proc = spawn(
    process.execPath,
    [viteBin, "preview", "--port", String(PORT), "--strictPort"],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("vite preview did not start")), 20000);
    proc.stdout.on("data", (buf) => {
      const plain = String(buf).replace(/\x1b\[[0-9;]*m/g, "");
      if (plain.includes("Local:")) {
        clearTimeout(timer);
        resolve(proc);
      }
    });
    proc.on("exit", (code) => reject(new Error(`vite preview exited (${code})`)));
  });
}

/** The single-origin synthetic backend (dist + API); resolves once /universe answers. */
function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT)], { stdio: ["ignore", "pipe", "pipe"] });
  proc.stderr.on("data", (b) => { const t = String(b); if (/Error|Traceback/.test(t)) console.error(t); });
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 60000;
    proc.on("exit", (code) => reject(new Error(`smoke server exited (${code})`)));
    const probe = async () => {
      try {
        const r = await fetch(`http://localhost:${PORT}/universe`);
        if (r.ok) return resolve(proc);
      } catch { /* not up yet */ }
      if (Date.now() > deadline) return reject(new Error("smoke server did not start"));
      setTimeout(probe, 500);
    };
    probe();
  });
}

const LIVE = existsSync(PY) && existsSync(SMOKE_SERVER);
const preview = LIVE ? await startLiveServer() : await startPreview();
console.log(LIVE ? "server: synthetic single-origin backend (live shell)" : "server: vite preview (mock shell)");
mkdirSync(OUT, { recursive: true });
let failures = 0;
const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: true,
  args: ["--no-first-run", "--disable-gpu"],
});

/** Assert the shell is healthy after a step; screenshot either way. */
async function check(page, pageErrors, name) {
  const crashed = await page.evaluate(() => document.body.innerText.includes("hit an error"));
  const empty = await page.evaluate(() => document.querySelector("main")?.innerText.trim() === "");
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  await page.screenshot({ path: `${OUT}${slug}.png` });
  if (crashed || empty || pageErrors.length > 0) {
    console.error(`FAIL ${name}: crashed=${crashed} empty=${empty} pageErrors=${pageErrors.length}`);
    pageErrors.forEach((e) => console.error(`  ${e}`));
    pageErrors.length = 0;
    failures += 1;
    return false;
  }
  console.log(`ok   ${name}`);
  return true;
}

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  // File ▸ Save as… must take the DOWNLOAD path (no native picker headless);
  // the <a download> click is captured in-page (blob text + filename) so the
  // round trip never depends on Chrome's headless download plumbing.
  const DL = `${OUT}downloads`;
  rmSync(DL, { recursive: true, force: true });
  mkdirSync(DL, { recursive: true });
  await page.evaluateOnNewDocument(() => {
    // The pickers live on Window.prototype — shadow them on the instance.
    for (const k of ["showSaveFilePicker", "showOpenFilePicker"]) {
      Object.defineProperty(window, k, { value: undefined, configurable: true, writable: true });
    }
    window.__smokeDownloads = [];
    const click = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
      if (!this.download) return click.call(this);
      const name = this.download;
      fetch(this.href).then((r) => r.blob()).then(async (b) => {
        const head = Array.from(new Uint8Array(await b.slice(0, 8).arrayBuffer()));
        window.__smokeDownloads.push({ name, text: await b.text(), head, size: b.size });
      });
    };
  });
  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(LIVE ? 2500 : 800);

  // 1. Lenses (the session auto-opens a preview tab for its default node).
  for (const lens of LENSES) {
    try {
      await clickAria(page, lens.name);
      await sleep(700);
      if (lens.subview) {
        const [sub] = await page.$$(`xpath/.//main//button[normalize-space()="${lens.subview}"]`);
        if (!sub) throw new Error(`subview "${lens.subview}" not found`);
        await sub.click();
        await sleep(700);
      }
      if (lens.hover && LIVE) {
        // Wait for the fetched surface, park the pointer on it, expect the badge.
        let svg = null;
        for (let i = 0; i < 40 && !svg; i++) { svg = await page.$("main svg.cursor-grab"); if (!svg) await sleep(250); }
        if (!svg) throw new Error("3D surface svg not found");
        const box = await svg.boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 6 });
        await sleep(400);
        const badge = await page.evaluate(() =>
          Array.from(document.querySelectorAll("main div.pointer-events-none"))
            .map((d) => d.textContent ?? "").find((t) => /^T /.test(t)) ?? null);
        if (!badge) throw new Error("no crosshair badge after hovering the surface");
        console.log(`     crosshair: ${badge}`);
      }
      await check(page, pageErrors, lens.slug ?? lens.name);
    } catch (err) {
      console.error(`FAIL ${lens.slug ?? lens.name}: ${err.message}`);
      failures += 1;
    }
  }

  // 2. Nodes pane → tab: click the first expiry row; the strip must show a tab.
  try {
    await clickAria(page, "Parametric");
    const rows = await page.$$('[role="tree"] [role="treeitem"][aria-selected]');
    if (rows.length === 0) throw new Error("no node rows in the Nodes pane");
    await rows[0].click();
    await sleep(500);
    const tabs = await page.$$('[role="tablist"] [role="tab"]');
    if (tabs.length === 0) throw new Error("no tab after clicking a node");
    await check(page, pageErrors, "nodes-pane-tab");
  } catch (err) {
    console.error(`FAIL nodes-pane-tab: ${err.message}`);
    failures += 1;
  }

  // 3. Menus open + close (Esc / backdrop).
  for (const m of MENUS) {
    try {
      await clickHeader(page, m);
      await check(page, pageErrors, `menu-${m}`);
      await page.keyboard.press("Escape");
      await page.mouse.click(700, 450); // click-away backdrop
      await sleep(150);
    } catch (err) {
      console.error(`FAIL menu-${m}: ${err.message}`);
      failures += 1;
    }
  }

  // 4. Dialogs render + Esc closes them.
  for (const d of DIALOGS) {
    try {
      await d.open(page);
      await sleep(400);
      const dialog = await page.$('[role="dialog"]');
      if (!dialog) throw new Error("no role=dialog rendered");
      await check(page, pageErrors, `dialog-${d.name}`);
      await page.keyboard.press("Escape");
      await sleep(200);
      if (await page.$('[role="dialog"]')) throw new Error("dialog did not close on Esc");
    } catch (err) {
      console.error(`FAIL dialog-${d.name}: ${err.message}`);
      failures += 1;
      await page.keyboard.press("Escape");
    }
  }
  // 5. Drag a node onto the Graph canvas (live only; wave 3 C5): darken the
  //    first node via its dot, drag its row onto the canvas (synthesized
  //    DragEvents with a real DataTransfer), expect it lit again on the wire.
  if (LIVE) {
    try {
      await clickAria(page, "Graph");
      await sleep(1500);
      const lit0 = await page.evaluate(async () => (await (await fetch("/universe/lit")).json()).nodes);
      const first = lit0[0];
      if (!first) throw new Error("no lit-map nodes");
      const rowSel = `#nodes-row-${`${first.ticker}|${first.expiry}`.replace(/[^a-zA-Z0-9]/g, "_")}`;
      await page.click(`${rowSel} button[aria-label^="lit"]`); // darken
      await sleep(600);
      const dark = (await page.evaluate(async () => (await (await fetch("/universe/lit")).json()).nodes))
        .find((n) => n.ticker === first.ticker && n.expiry === first.expiry);
      if (!dark || dark.lit) throw new Error("node did not darken before the drag");
      const dropped = await page.evaluate(async (sel) => {
        const row = document.querySelector(sel);
        const zone = document.querySelector('[data-drop-zone="graph-canvas"]');
        if (!row || !zone) return "missing row/zone";
        const dt = new DataTransfer();
        row.dispatchEvent(new DragEvent("dragstart", { bubbles: true, dataTransfer: dt }));
        zone.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt }));
        await new Promise((r) => setTimeout(r, 120)); // React commits the halo
        const halo = zone.className.includes("ring-2");
        zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
        return halo ? "ok" : `no halo on dragover (types: ${Array.from(dt.types).join(",")})`;
      }, rowSel);
      if (dropped !== "ok") throw new Error(dropped);
      await sleep(800);
      const relit = (await page.evaluate(async () => (await (await fetch("/universe/lit")).json()).nodes))
        .find((n) => n.ticker === first.ticker && n.expiry === first.expiry);
      if (!relit || !relit.lit) throw new Error("dropped node is not lit on the wire");
      await check(page, pageErrors, "drag-to-light");
    } catch (err) {
      console.error(`FAIL drag-to-light: ${err.message}`);
      failures += 1;
    }
  }

  // 5a. Split editors (wave 3 C3): Ctrl+\ splits, Ctrl+Enter on a tree row
  //     opens a second node in the other group; two tab lists must exist and
  //     the two groups must show DIFFERENT nodes (their chart titles differ).
  //     Then the third group (follow-on): a second Ctrl+\ adds a group, a
  //     third node opens there, and Ctrl+\ at the cap folds back to ONE.
  try {
    await clickAria(page, "Parametric");
    await sleep(600);
    await page.keyboard.down("Control"); await page.keyboard.press("Backslash"); await page.keyboard.up("Control");
    await sleep(600);
    let lists = await page.$$('[role="tablist"]');
    if (lists.length !== 2) throw new Error(`expected 2 tab lists after Ctrl+\\, got ${lists.length}`);
    // Focus the tree, move to the second expiry row of the first ticker, Ctrl+Enter.
    await page.focus('[role="tree"]');
    await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowDown");
    await page.keyboard.down("Control"); await page.keyboard.press("Enter"); await page.keyboard.up("Control");
    await sleep(2500);
    const titles = await page.evaluate(() =>
      Array.from(document.querySelectorAll("[data-editor-group] main h2")).map((h) => h.textContent?.trim() ?? ""));
    if (titles.length < 2 || titles[0] === titles[1]) throw new Error(`groups do not show two nodes: ${JSON.stringify(titles)}`);
    console.log(`     groups: ${titles.join(" | ")}`);
    await check(page, pageErrors, "split-editors");
    // Third group (N ≤ 3): Ctrl+\ from two groups ADDS one after the focused
    // group. Focus the MIDDLE group (a click) so Ctrl+Enter's "beside" target
    // — the next group — is the fresh third one, then open the next tree row
    // there: three DISTINCT chart titles.
    await page.keyboard.down("Control"); await page.keyboard.press("Backslash"); await page.keyboard.up("Control");
    await sleep(600);
    lists = await page.$$('[role="tablist"]');
    if (lists.length !== 3) throw new Error(`expected 3 tab lists after a second Ctrl+\\, got ${lists.length}`);
    const panes = await page.$$("[data-editor-group]");
    if (panes.length !== 3) throw new Error(`expected 3 editor groups, got ${panes.length}`);
    await page.click('[data-editor-group="1"] [role="tablist"]');
    await page.focus('[role="tree"]');
    await page.keyboard.press("ArrowDown");
    await page.keyboard.down("Control"); await page.keyboard.press("Enter"); await page.keyboard.up("Control");
    await sleep(2500);
    const titles3 = await page.evaluate(() =>
      Array.from(document.querySelectorAll("[data-editor-group] main h2")).map((h) => h.textContent?.trim() ?? ""));
    if (new Set(titles3).size < 3) throw new Error(`groups do not show three nodes: ${JSON.stringify(titles3)}`);
    console.log(`     groups: ${titles3.join(" | ")}`);
    await check(page, pageErrors, "split-editors-3");
    // At the cap, Ctrl+\ folds every group back into one (toggleSplit).
    await page.keyboard.down("Control"); await page.keyboard.press("Backslash"); await page.keyboard.up("Control");
    await sleep(400);
    lists = await page.$$('[role="tablist"]');
    if (lists.length !== 1) throw new Error(`expected 1 tab list after unsplit, got ${lists.length}`);
  } catch (err) {
    console.error(`FAIL split-editors: ${err.message}`);
    failures += 1;
    await page.keyboard.press("Escape");
  }

  // 5b. Export chart as PNG (wave 3 A3) through the command palette: the
  //     active Parametric chart rasterizes to a captured .png download.
  try {
    await clickAria(page, "Parametric");
    await sleep(800);
    await page.keyboard.down("Control"); await page.keyboard.press("KeyK"); await page.keyboard.up("Control");
    await sleep(300);
    await page.keyboard.type("chart as png");
    await sleep(200);
    await page.keyboard.press("Enter");
    let png = null;
    for (let i = 0; i < 40 && !png; i++) {
      await sleep(250);
      png = await page.evaluate(() => window.__smokeDownloads.find((d) => d.name.endsWith(".png")) ?? null);
    }
    if (!png) {
      const footer = await page.evaluate(() => document.querySelector("footer")?.innerText ?? "");
      throw new Error(`no .png download (status bar: ${footer})`);
    }
    // <ticker>_<expiry>_<view>.png — the view is whatever the tab remembers (C2).
    if (!/^[A-Z]+_\d{4}-\d{2}-\d{2}_[a-z-]+\.png$/.test(png.name)) throw new Error(`unexpected png name ${png.name}`);
    if (png.head.slice(0, 4).join(",") !== "137,80,78,71") throw new Error(`download is not a PNG (head ${png.head.join(",")}, ${png.size} bytes)`);
    await check(page, pageErrors, "export-chart-png");
  } catch (err) {
    console.error(`FAIL export-chart-png: ${err.message}`);
    failures += 1;
    await page.keyboard.press("Escape");
  }

  // 6. Snapshot file round trip (live only; wave 3 A2): File ▸ Save snapshot…
  //    (captured download) → File ▸ Open snapshot… via the file chooser → the
  //    File data source is active and the status bar names it.
  if (LIVE) {
    try {
      await clickHeader(page, "File");
      await clickText(page, "Save snapshot…");
      let dl = null;
      for (let i = 0; i < 60 && !dl; i++) {
        await sleep(250);
        dl = await page.evaluate(() => window.__smokeDownloads.find((d) => d.name.endsWith(".volfit-snapshot.json")) ?? null);
      }
      if (!dl) {
        const footer = await page.evaluate(() => document.querySelector("footer")?.innerText ?? "");
        throw new Error(`no snapshot download (status bar: ${footer})`);
      }
      const bundle = JSON.parse(dl.text);
      if (bundle.schema !== "volfit-snapshot/1" || !bundle.tickers?.length) throw new Error("snapshot bundle malformed");
      writeFileSync(`${DL}/${dl.name}`, dl.text);
      await clickHeader(page, "File");
      const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }), clickText(page, "Open snapshot…")]);
      await chooser.accept([`${DL}/${dl.name}`]);
      await sleep(2500);
      const ds = await page.evaluate(async () => (await (await fetch("/datasources")).json()));
      if (ds.active !== "file") throw new Error(`active source is ${ds.active}, not file`);
      const footer = await page.evaluate(() => document.querySelector("footer")?.innerText ?? "");
      if (!footer.includes("File ·")) throw new Error(`status bar does not name the file source: ${footer}`);
      await check(page, pageErrors, "snapshot-roundtrip");
    } catch (err) {
      console.error(`FAIL snapshot-roundtrip: ${err.message}`);
      failures += 1;
      await page.keyboard.press("Escape");
    }
  }

  // 7. Workspace file round trip (live only): Save as… → download; Open… via
  //    the file chooser; the status bar names the workspace.
  if (LIVE) {
    try {
      await clickHeader(page, "File");
      await clickText(page, "Save workspace as…");
      let dl = null;
      for (let i = 0; i < 40 && !dl; i++) {
        await sleep(250);
        dl = await page.evaluate(() => window.__smokeDownloads.find((d) => d.name.endsWith(".volfit.json")) ?? null);
      }
      if (!dl) {
        const footer = await page.evaluate(() => document.querySelector("footer")?.innerText ?? "");
        throw new Error(`no .volfit.json download after Save as… (status bar: ${footer})`);
      }
      const file = dl.name;
      writeFileSync(`${DL}/${file}`, dl.text);
      const bundle = JSON.parse(readFileSync(`${DL}/${file}`, "utf8"));
      if (bundle.schema !== "volfit-workspace/1" || !bundle.backend || !bundle.shell) {
        throw new Error(`downloaded bundle malformed: ${Object.keys(bundle)}`);
      }
      await check(page, pageErrors, "workspace-save-as");
      // Open it back through the <input type=file> fallback (file chooser).
      await clickHeader(page, "File");
      const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }), clickText(page, "Open workspace…")]);
      await chooser.accept([`${DL}/${file}`]);
      await sleep(1500);
      const chip = await page.evaluate(() => document.querySelector("footer")?.innerText ?? "");
      const name = file.replace(/\.volfit\.json$/, "");
      if (!chip.includes(name)) throw new Error(`status bar does not name the opened workspace (${name}): ${chip}`);
      await check(page, pageErrors, "workspace-open");
    } catch (err) {
      console.error(`FAIL workspace-roundtrip: ${err.message}`);
      failures += 1;
      await page.keyboard.press("Escape");
    }
  }
} finally {
  await browser.close();
  preview.kill();
}

if (failures > 0) {
  console.error(`\nUI smoke: ${failures} step(s) failed (screenshots in .smoke/)`);
  process.exit(1);
}
console.log(`\nUI smoke: shell, ${LENSES.length} lens steps, ${MENUS.length} menus, ${DIALOGS.length} dialogs${LIVE ? ", workspace file round trip" : ""} render (screenshots in .smoke/)`);

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
      fetch(this.href).then((r) => r.text()).then((text) => window.__smokeDownloads.push({ name, text }));
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
  // 5. Workspace file round trip (live only): Save as… → download; Open… via
  //    the file chooser; the status bar names the workspace.
  if (LIVE) {
    try {
      await clickHeader(page, "File");
      await clickText(page, "Save as…");
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
      const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }), clickText(page, "Open…")]);
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

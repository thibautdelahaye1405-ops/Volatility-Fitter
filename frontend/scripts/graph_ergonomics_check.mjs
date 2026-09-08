// Headless-Edge LIVE check of the Graph lens after the GRAPH ERGONOMICS ARC
// (2026-09-07) on the synthetic single-origin smoke server
// (backend/smoke_server.py):
//   1. API bootstrap: fit every node of the first ticker, darken one, save
//      the priors so a Run has a baseline;
//   2. Graph lens: Layered is the default segment (Smooth field absent), the
//      Coupling pane shows the Level-0 sliders, the canvas draws arrows;
//   3. click a calendar hop → the relation card; drag β → the draft is staged
//      (GET /graph/config/messages) and the config pill counts the edit;
//   4. Shift-drag node → node adds a relation; Delete removes it;
//   5. Run → posterior summary; Live → a preview-tagged re-solve on a dial;
//   6. Focus hides the panes (Esc restores); a ticker label collapses its pod;
//      the Relations tab lists the rows; Apply activates the draft.
// Port 4194 (never 4190 — the WHATWG fetch bad-ports list). Screenshots in
// .smoke/graph-ergo-*.png. Prereqs: npm run build, Edge, ../.venv.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4194;
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const BASE = `http://localhost:${PORT}`;

if (!existsSync(PY) || !existsSync(SMOKE_SERVER)) throw new Error("the synthetic smoke server needs ../.venv");

function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT)], { stdio: ["ignore", "pipe", "pipe"] });
  proc.stderr.on("data", (b) => { const t = String(b); if (/Error|Traceback/.test(t)) console.error(t); });
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 60000;
    proc.on("exit", (code) => reject(new Error(`smoke server exited (${code})`)));
    const probe = async () => {
      try { const r = await fetch(`${BASE}/universe`); if (r.ok) return resolve(proc); } catch { /* not up */ }
      if (Date.now() > deadline) return reject(new Error("smoke server did not start"));
      setTimeout(probe, 500);
    };
    probe();
  });
}

async function api(method, path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method, headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function waitFor(page, fn, what, ms = 20000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn)) return;
    await sleep(200);
  }
  throw new Error(`timed out waiting for ${what}`);
}

const server = await startLiveServer();
mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
let failures = 0;
const step = async (name, fn) => {
  try { await fn(); console.log(`ok   ${name}`); } catch (err) { failures += 1; console.error(`FAIL ${name}: ${err.message}`); }
};
const shot = (page, name) => page.screenshot({ path: `${OUT}graph-ergo-${name}.png` });

/** Centre of an element in page coordinates. */
async function centre(page, selector) {
  const box = await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }, selector);
  if (!box) throw new Error(`no element ${selector}`);
  return box;
}

/** Set a React-controlled range input's value (native setter + input event). */
async function setRange(page, selector, value) {
  await page.evaluate((sel, v) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`no range ${sel}`);
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(el, String(v));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, selector, value);
}

try {
  // 1. API bootstrap
  const universe = await api("GET", "/universe");
  const ticker = universe.tickers[0];
  const expiries = universe.expiries[ticker].map((e) => e.expiry);
  for (const e of expiries) await api("GET", `/smiles/${ticker}/${e}`);
  const dark = expiries[Math.min(2, expiries.length - 1)];
  await api("PUT", `/universe/lit/${ticker}/${dark}`, { lit: false });
  await api("POST", "/priors/save-all");
  console.log(`bootstrap: ${universe.tickers.length} tickers · ${ticker} ${expiries.length} expiries · dark ${dark}`);

  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 45000 });
  await page.keyboard.press("Escape"); // first-run Welcome
  await sleep(300);

  // 2. Graph lens
  await step("graph lens: Layered default, Level-0 sliders, arrows", async () => {
    await page.click('[aria-label="Graph"]');
    await waitFor(page, () => document.querySelectorAll('[data-testid="graph-canvas"] [data-node]').length > 3, "canvas nodes", 60000);
    await sleep(800);
    const seg = await page.evaluate(() => [...document.querySelectorAll("button")].map((b) => b.textContent?.trim()));
    if (!seg.includes("Layered") || !seg.includes("Precision")) throw new Error("operator segments missing");
    if (seg.includes("Smooth field")) throw new Error("Smooth field is visible at Level 0");
    if (!(await page.$('[data-testid="slider-cal"]')) || !(await page.$('[data-testid="slider-cross"]'))) throw new Error("Level-0 sliders missing");
    const arrows = await page.evaluate(() => document.querySelectorAll("[data-calendar] polygon").length);
    if (arrows === 0) throw new Error("no calendar arrow heads");
    await shot(page, "1-lens");
  });

  // 2b. a SHORT pane (2026-09-08 report): every toolbar button must stay
  //     inside the chart area — the Focus button in particular.
  await step("short pane: the toolbar (Focus first) stays inside the chart area", async () => {
    await page.setViewport({ width: 1400, height: 720 });
    await sleep(500);
    const box = await page.evaluate(() => {
      // DOMRects do not serialize across the bridge — copy the numbers.
      const plain = (r) => (r ? { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height } : null);
      const chart = plain(document.querySelector('[data-testid="graph-canvas"]')?.getBoundingClientRect());
      const focus = plain(document.querySelector('[data-testid="tool-focus"]')?.getBoundingClientRect());
      const fit = plain([...document.querySelectorAll('[data-testid="canvas-toolbar"] button')].pop()?.getBoundingClientRect());
      return { chart, focus, fit };
    });
    const inside = (r) => r && box.chart && r.top >= box.chart.top && r.bottom <= box.chart.bottom && r.right <= box.chart.right && r.left >= box.chart.left;
    if (!inside(box.focus) || !inside(box.fit)) throw new Error(`toolbar clipped: chart ${JSON.stringify(box.chart)} focus ${JSON.stringify(box.focus)}`);
    if (box.chart.height < 120) throw new Error(`chart area too short to be meaningful (${box.chart.height}px)`);
    await shot(page, "1b-short-pane");
    await page.setViewport({ width: 1600, height: 1000 });
    await sleep(500);
  });

  // 3. relation card via a calendar hop; β drag stages the draft
  let firstKey = null;
  await step("calendar hop → relation card; β slider stages the draft; pill counts 1 edit", async () => {
    const hop = await page.evaluate(() => {
      const g = document.querySelector("[data-calendar]");
      const lines = g?.querySelectorAll("line") ?? [];
      const hit = lines[lines.length - 1];
      if (!hit) return null;
      const r = hit.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, id: g.getAttribute("data-calendar") };
    });
    if (!hop) throw new Error("no calendar hop");
    await page.mouse.click(hop.x, hop.y);
    await waitFor(page, () => !!document.querySelector('[data-testid="relation-card"]'), "relation card");
    firstKey = await page.evaluate(() => document.querySelector("[data-relation-row]")?.getAttribute("data-relation-row") ?? null);
    await setRange(page, '[data-testid="slider-beta"]', 1.35);
    await sleep(900); // the draft debounce
    const cfg = await api("GET", "/graph/config/messages");
    const rows = cfg.draft?.rows ?? [];
    const edited = rows.find((r) => Math.abs(r.betaAtmVol - 1.35) < 1e-9);
    if (!edited) throw new Error(`draft not staged (draft rows ${rows.length})`);
    // A first draft against no active config reads "new draft"; later edits count.
    await waitFor(page, () => /new draft|1 edit/.test(document.querySelector('[data-testid="config-chip"]')?.textContent ?? ""), "config pill edit marker");
    await shot(page, "2-relation-card");
  });

  // 4. connect gestures: Shift-drag, the Connect TOOL, a PLAIN drag; Delete
  const nodeCentres = () =>
    page.evaluate(() =>
      [...document.querySelectorAll('[data-testid="graph-canvas"] [data-node]')].map((g) => {
        const c = g.querySelector("circle:last-of-type");
        const r = c.getBoundingClientRect();
        return { key: g.getAttribute("data-node"), x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }),
    );
  const dragNode = async (a, b) => {
    await page.mouse.move(a.x, a.y);
    await page.mouse.down();
    await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 6 });
    await page.mouse.move(b.x, b.y, { steps: 6 });
    await page.mouse.up();
  };
  const rowExists = async (a, b) => {
    const [st, se] = a.key.split("|");
    const [tt, te] = b.key.split("|");
    return (await api("GET", "/graph/edges/messages")).edges.some(
      (r) => r.sourceTicker === st && r.sourceExpiry === se && r.targetTicker === tt && r.targetExpiry === te,
    );
  };
  await step("Connect TOOL drag adds a relation; a PLAIN drag adds another; Delete removes", async () => {
    const nodes = await nodeCentres();
    const spy = nodes.filter((n) => n.key.startsWith(`${ticker}|`));
    const other = nodes.filter((n) => !n.key.startsWith(`${ticker}|`));
    // tool: ticker's LAST expiry → other ticker's LAST expiry (no auto row there)
    const a = spy[spy.length - 1];
    const b = other[other.length - 1];
    if (await rowExists(a, b)) throw new Error("fixture: the tool pair already exists");
    await page.click('[data-testid="tool-connect"]');
    await dragNode(a, b);
    await waitFor(page, () => !!document.querySelector('[data-testid="relation-card"]'), "relation card after tool connect");
    await sleep(900);
    if (!(await rowExists(a, b))) throw new Error("the Connect tool did not stage a row");
    await page.keyboard.press("Escape"); // exits the tool + clears the selection
    await sleep(200);
    // plain drag: other ticker's FIRST expiry → ticker's LAST expiry
    const c = other[0];
    const before = await rowExists(c, a);
    await page.keyboard.press("Escape");
    await dragNode(c, a);
    await waitFor(page, () => !!document.querySelector('[data-testid="relation-card"]'), "relation card after plain drag");
    await sleep(900);
    if (!before && !(await rowExists(c, a))) throw new Error("a plain drag did not stage a row");
    await shot(page, "3b-plain-drag");
    await page.keyboard.press("Delete");
    await sleep(900);
    if (await rowExists(c, a)) throw new Error("Delete did not remove the plain-drag row");
  });

  await step("Shift-drag node → node adds a relation; Delete removes it", async () => {
    const nodes = await page.evaluate(() =>
      [...document.querySelectorAll('[data-testid="graph-canvas"] [data-node]')].map((g) => {
        const c = g.querySelector("circle:last-of-type");
        const r = c.getBoundingClientRect();
        return { key: g.getAttribute("data-node"), x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }),
    );
    const a = nodes.find((n) => n.key.startsWith(`${ticker}|`));
    const b = nodes.find((n) => !n.key.startsWith(`${ticker}|`)) ?? nodes.find((n) => n.key !== a.key);
    const before = (await api("GET", "/graph/edges/messages")).edges.length;
    await page.keyboard.down("Shift");
    await page.mouse.move(a.x, a.y);
    await page.mouse.down();
    await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 5 });
    await page.mouse.move(b.x, b.y, { steps: 5 });
    await page.mouse.up();
    await page.keyboard.up("Shift");
    await waitFor(page, () => !!document.querySelector('[data-testid="relation-card"]'), "relation card after connect");
    await sleep(900);
    const after = (await api("GET", "/graph/edges/messages")).edges;
    const [st, se] = a.key.split("|");
    const [tt, te] = b.key.split("|");
    const added = after.find((r) => r.sourceTicker === st && r.sourceExpiry === se && r.targetTicker === tt && r.targetExpiry === te);
    if (!added) throw new Error(`connect did not stage a row (${before} → ${after.length})`);
    await shot(page, "3-connect");
    await page.keyboard.press("Delete");
    await sleep(900);
    const gone = (await api("GET", "/graph/edges/messages")).edges.some((r) => r.sourceTicker === st && r.sourceExpiry === se && r.targetTicker === tt && r.targetExpiry === te);
    if (gone) throw new Error("Delete did not remove the row");
  });

  // 5. Run + Live preview
  await step("Run solves the draft; Live re-solves as a preview on a dial", async () => {
    await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Run")?.click());
    await waitFor(page, () => !!document.querySelector('[data-testid="run-summary"]'), "run summary", 120000);
    await waitFor(page, () => [...document.querySelectorAll("button")].some((b) => b.textContent?.trim() === "Run" && !b.disabled), "Run settled", 120000);
    const summary = await page.evaluate(() => document.querySelector('[data-testid="run-summary"]')?.textContent ?? "");
    if (/preview/.test(summary)) throw new Error("a committed Run is tagged preview");
    const diagActive = await page.evaluate(() =>
      [...document.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Diagnostics")?.className.includes("text-slate-100") ?? false,
    );
    if (!diagActive) throw new Error("the drawer did not reveal Diagnostics after Run");
    await shot(page, "4-run");
    await page.click('[data-testid="live-toggle"]');
    await setRange(page, '[data-testid="slider-cross"]', Math.log10(1)); // σ 1 pt
    await waitFor(page, () => /preview/.test(document.querySelector('[data-testid="run-summary"]')?.textContent ?? ""), "preview tag", 120000);
    await page.click('[data-testid="live-toggle"]'); // off
    await shot(page, "5-live");
  });

  // 6. Focus, collapse, Relations tab, Apply
  await step("Focus hides the panes, re-fits the graph, keeps editing (floating card); Esc restores", async () => {
    const before = await page.evaluate(() => document.querySelector('[data-testid="graph-canvas"] svg > g')?.getAttribute("transform") ?? "");
    await page.click('[data-testid="tool-focus"]');
    await sleep(400);
    if (await page.$('[data-testid="policy-pane"]')) throw new Error("pane still visible in Focus");
    const after = await page.evaluate(() => document.querySelector('[data-testid="graph-canvas"] svg > g')?.getAttribute("transform") ?? "");
    if (after === before) throw new Error("the graph did not re-fit to the focused canvas");
    // click an arrow: the card floats over the canvas
    const hop = await page.evaluate(() => {
      const g = document.querySelector("[data-calendar]");
      const lines = g?.querySelectorAll("line") ?? [];
      const hit = lines[lines.length - 1];
      const r = hit.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    });
    await page.mouse.click(hop.x, hop.y);
    await waitFor(page, () => !!document.querySelector('[data-testid="canvas-overlay"] [data-testid="relation-card"]'), "floating relation card");
    await shot(page, "6-focus");
    await page.keyboard.press("Escape"); // closes the card
    await sleep(200);
    if (await page.$('[data-testid="canvas-overlay"]')) throw new Error("Esc did not close the floating card");
    await page.keyboard.press("Escape");
    await sleep(200);
    if (!(await page.$('[data-testid="policy-pane"]'))) throw new Error("pane did not come back");
    const label = await centre(page, `[data-pod="${ticker}"]`);
    await page.mouse.click(label.x, label.y);
    await sleep(300);
    if (!(await page.$(`[data-node="${ticker}|*"]`))) throw new Error("pod did not collapse");
    await page.mouse.click(label.x, label.y); // expand again (label moves little)
    await sleep(300);
  });

  await step("Relations tab lists the rows; Apply activates the draft", async () => {
    await page.click('[data-testid="open-relations"]');
    await waitFor(page, () => document.querySelectorAll("[data-relation-row]").length > 0, "relation rows");
    await shot(page, "7-relations");
    const before = (await api("GET", "/graph/config/messages")).active?.version ?? 0;
    await page.click('[data-testid="config-chip"]');
    await sleep(200);
    await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Apply")?.click());
    await sleep(1500);
    const after = (await api("GET", "/graph/config/messages")).active?.version ?? 0;
    if (!(after > before)) throw new Error(`Apply did not activate (v${before} → v${after})`);
    await shot(page, "8-applied");
  });

  if (pageErrors.length > 0) {
    failures += 1;
    console.error(`FAIL page errors:\n${pageErrors.join("\n")}`);
  }
} finally {
  await browser.close();
  server.kill();
}
if (failures > 0) {
  console.error(`${failures} failure(s)`);
  process.exit(1);
}
console.log("graph ergonomics check: all steps passed");

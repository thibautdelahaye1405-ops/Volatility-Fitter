// Headless-Edge LIVE check of the SERIES lens (SERIES ARC S4) on the synthetic
// single-origin smoke server (backend/smoke_server.py, throw-away DB with a
// store, so series persist):
//   1. through the API: create a LIVE series on the first ticker whose instants
//      lie in the past (every frame is due at once), two lanes from the
//      presets (LQD free + LQD prior), start it and wait until it is done —
//      frames harvested through the app's own refresh, lanes calibrated;
//   2. open the app, switch to the Series lens (Alt+6), expect the picker to
//      list the series, the transport bar and a smile with the lanes drawn;
//   3. play: the readout's frame index advances; scrub to the last frame;
//      keys: Home / ArrowRight / Space; the Frames stage lists every frame;
//   4. the New series dialog opens and closes (Escape).
// Port 4197 — NOT 4190 (the WHATWG fetch bad-ports list). Screenshots in
// .smoke/series-*.png. Prereqs: npm run build, Edge, ../.venv.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4197;
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
    method, headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function clickAria(page, label, scope = "") {
  const btn = await page.$(`${scope} button[aria-label="${label}"]`.trim());
  if (!btn) throw new Error(`button[aria-label="${label}"] not found`);
  await btn.click();
  await sleep(500);
}

async function waitFor(page, fn, what, ms = 20000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn)) return;
    await sleep(200);
  }
  throw new Error(`timed out waiting for ${what}`);
}

const readout = (page) => page.evaluate(() => {
  const el = document.querySelector('[data-testid="series-transport"]');
  return el ? el.textContent : "";
});

const server = await startLiveServer();
mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
let failures = 0;
const step = async (name, fn) => {
  try { await fn(); console.log(`ok   ${name}`); } catch (err) { failures += 1; console.error(`FAIL ${name}: ${err.message}`); }
};

try {
  // 1. A live series through the API: 6 frames one minute apart, all in the past.
  const universe = await api("GET", "/universe");
  const ticker = universe.tickers[0];
  const presets = await api("GET", "/series/presets");
  const lanes = presets.filter((p) => p.id === "lqd_free" || p.id === "lqd_prior");
  const start = new Date(Date.now() - 6 * 60 * 1000).toISOString();
  const created = await api("POST", "/series", {
    name: `${ticker} smoke series`, ticker, mode: "live",
    clock: { start, step: "1m", count: 6, sessionOnly: false, timeOfDay: "15:45", tz: "America/New_York", warmupFrames: 0 },
    ladder: { policy: "pinned", expiries: [], maxExpiries: 3 }, fitMode: "mid", lanes, note: "smoke",
  });
  console.log(`series ${created.id}: estimate ${JSON.stringify(created.estimate).slice(0, 160)}`);
  await api("POST", `/series/${created.id}/start`);
  const deadline = Date.now() + 120000;
  let status;
  do {
    await sleep(1000);
    status = await api("GET", `/series/${created.id}/status`);
  } while (Date.now() < deadline && !["done", "failed", "cancelled"].includes(status.progress.status));
  console.log(`series status: ${JSON.stringify(status.progress).slice(0, 200)}`);
  if (status.progress.status !== "done") throw new Error(`the series did not finish: ${status.progress.status}`);
  const frame = await api("GET", `/series/${created.id}/frame/0`);
  if (!frame.expiries.length || !Object.keys(frame.lanes).length) throw new Error("frame 0 has no market / lanes");

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape"); // the first-run Welcome
  await sleep(400);

  // 2. The lens + the picker + the transport bar.
  await step("series-lens-opens", async () => {
    await clickAria(page, "Series");
    await waitFor(page, () => !!document.querySelector('[data-testid="series-transport"]'), "the transport bar");
    const picked = await page.evaluate(() => {
      const sel = document.querySelector('main select[aria-label="Series"]');
      return sel ? sel.options[sel.selectedIndex]?.textContent : null;
    });
    if (!picked || !/smoke series/.test(picked)) throw new Error(`the picker does not show the series (${picked})`);
    await waitFor(page, () => !!document.querySelector("main svg path[data-lane]"), "a lane curve on the smile");
    await page.screenshot({ path: `${OUT}series-lens.png` });
  });

  // 3. Play, scrub, keys.
  await step("series-play-advances", async () => {
    const before = await readout(page);
    await clickAria(page, "Play", "main");
    await sleep(1800); // 1× = 500 ms per frame
    await clickAria(page, "Pause", "main");
    const after = await readout(page);
    const idx = (s) => { const m = /frame\s+(\d+)\s*\/\s*(\d+)/.exec(s); return m ? Number(m[1]) : NaN; };
    if (!(idx(after) > idx(before))) throw new Error(`the readout did not advance: "${before}" -> "${after}"`);
    await page.screenshot({ path: `${OUT}series-playing.png` });
  });
  await step("series-scrub-and-keys", async () => {
    await page.evaluate(() => {
      const input = document.querySelector('main input[aria-label="Frame"]');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(input, input.max);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await sleep(500);
    const last = await readout(page);
    if (!/frame\s+6\s*\/\s*6/.test(last)) throw new Error(`scrub to the end failed: "${last}"`);
    await page.focus('[data-testid="series-transport"]');
    await page.keyboard.press("Home");
    await sleep(400);
    await page.keyboard.press("ArrowRight");
    await sleep(400);
    const stepped = await readout(page);
    if (!/frame\s+2\s*\/\s*6/.test(stepped)) throw new Error(`Home + ArrowRight did not land on frame 2: "${stepped}"`);
  });

  // 4. The Frames stage + the dialog.
  await step("series-frames-stage-and-dialog", async () => {
    const [tab] = await page.$$('xpath/.//main//button[normalize-space()="Frames"]');
    if (!tab) throw new Error("the Frames stage tab is missing");
    await tab.click();
    await sleep(500);
    const rows = await page.$$eval("main table tbody tr", (trs) => trs.length);
    if (rows !== 6) throw new Error(`the frames table lists ${rows} rows, not 6`);
    await page.screenshot({ path: `${OUT}series-frames.png` });
    const [btn] = await page.$$('xpath/.//main//button[starts-with(normalize-space(), "New series")]');
    if (!btn) throw new Error("the New series button is missing");
    await btn.click();
    await sleep(600);
    await waitFor(page, () => !!document.querySelector('[role="dialog"]'), "the dialog");
    await page.screenshot({ path: `${OUT}series-dialog.png` });
    await page.keyboard.press("Escape");
    await sleep(400);
  });

  if (pageErrors.length) { failures += 1; console.error(`page errors: ${pageErrors.join(" | ")}`); }
} finally {
  await browser.close();
  server.kill();
}
console.log(failures ? `${failures} check(s) FAILED` : "series check: all green");
process.exit(failures ? 1 : 0);

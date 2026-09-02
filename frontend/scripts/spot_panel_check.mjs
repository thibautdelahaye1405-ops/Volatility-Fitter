// Headless-Edge check of the Spot move card (Parametric aside) on the LIVE
// synthetic single-origin server (backend/smoke_server.py, throw-away DB):
//   1. the three spot readouts render (Calibrated · Market · Scenario);
//   2. the ± fine-tune buttons move the dial (0.1 % / Shift 1 %), the backend
//      shift follows ("manual") and the smile's market frame forward moves;
//   3. Re-anchor clears the dial, narrates the background job and the chart
//      keeps a fitted curve throughout (never blank);
// Screenshots land in .smoke/spot-*.png. Prereqs: `npm run build`, Edge, ../.venv.
//   node scripts/spot_panel_check.mjs
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4189; // off the ui_smoke port so both can run
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT)], { stdio: ["ignore", "pipe", "pipe"] });
  proc.stderr.on("data", (b) => { const t = String(b); if (/Error|Traceback/.test(t)) console.error(t); });
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 60000;
    proc.on("exit", (code) => reject(new Error(`smoke server exited (${code})`)));
    const probe = async () => {
      try { if ((await fetch(`http://localhost:${PORT}/universe`)).ok) return resolve(proc); } catch { /* not up */ }
      if (Date.now() > deadline) return reject(new Error("smoke server did not start"));
      setTimeout(probe, 500);
    };
    probe();
  });
}

if (!existsSync(PY) || !existsSync(SMOKE_SERVER)) throw new Error("needs ../.venv and backend/smoke_server.py");
const server = await startLiveServer();
mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
let failures = 0;
const fail = (msg) => { failures += 1; console.error(`FAIL ${msg}`); };

/** The Spot move card's rows as {label: value}. */
const readRows = (page) => page.evaluate(() => {
  const h = Array.from(document.querySelectorAll("main h3")).find((e) => e.textContent.trim() === "Spot move");
  const card = h?.closest("section");
  const out = {};
  if (!card) return out;
  for (const row of card.querySelectorAll("div.flex.items-center.justify-between.gap-2")) {
    const [label, value] = row.querySelectorAll(":scope > span");
    if (label && value) out[label.childNodes[0].textContent.trim()] = value.textContent.trim();
  }
  return out;
});
const buttonText = (page, re) => page.evaluate((src) => {
  const rx = new RegExp(src);
  return Array.from(document.querySelectorAll("main button")).map((b) => b.textContent.trim()).find((t) => rx.test(t)) ?? null;
}, re.source);
const api = (page, path) => page.evaluate(async (p) => (await fetch(p)).json(), path);
/** Screenshot, tolerating a busy renderer (a missed shot is a warning, not a failure). */
const shot = async (page, name) => { try { await page.screenshot({ path: `${OUT}${name}` }); } catch (e) { console.warn(`warn: screenshot ${name}: ${e.message}`); } };

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape"); // the first-run Welcome
  await sleep(300);
  await page.click('button[aria-label="Parametric"]');
  await sleep(1500);

  const universe = await api(page, "/universe");
  const ticker = universe.tickers[0];
  const expiry = universe.expiries[ticker][1].expiry;
  const smile0 = await api(page, `/smiles/${ticker}/${expiry}`);
  const rows0 = await readRows(page);
  console.log("rows (initial):", rows0);
  await shot(page, "spot-1-initial.png");
  if (!/^\d+\.\d\d$/.test(rows0.Calibrated ?? "")) fail(`Calibrated row missing: ${JSON.stringify(rows0)}`);
  if (!/\s0\.00%/.test(rows0.Market ?? "")) fail(`Market row should show the chain spot at 0.00%: ${rows0.Market}`);
  if (!/\s0\.0%/.test(rows0.Scenario ?? "")) fail(`Scenario row should start at 0.0%: ${rows0.Scenario}`);
  if (!smile0.hasFit) fail("the synthetic node has no fit before the dial test");

  // 2. The dial: 10 fine clicks (+1.0 %) and one Shift click (+1 %) => +2.0 %.
  const plus = await page.$('button[aria-label="Spot up 0.1 percent"]');
  if (!plus) throw new Error("the + fine-tune button is missing");
  for (let i = 0; i < 10; i++) { await plus.click(); await sleep(60); }
  await page.keyboard.down("Shift"); await plus.click(); await page.keyboard.up("Shift");
  await sleep(900); // debounce + PUT + view refetch
  const rows1 = await readRows(page);
  const spot1 = await api(page, `/spot/${ticker}`);
  const smile1 = await api(page, `/smiles/${ticker}/${expiry}`);
  console.log("rows (after +2.0%):", rows1, "| backend shift:", spot1.spotReturn, spot1.shiftSource);
  await shot(page, "spot-2-dial.png");
  if (Math.abs(spot1.spotReturn - 0.02) > 1e-9) fail(`backend shift is ${spot1.spotReturn}, expected 0.02`);
  if (spot1.shiftSource !== "manual") fail(`shift source is ${spot1.shiftSource}, expected manual`);
  if (!/\+2\.0%/.test(rows1.Scenario ?? "")) fail(`Scenario row did not follow the dial: ${rows1.Scenario}`);
  const ratio = smile1.market.forward / smile0.market.forward;
  if (Math.abs(ratio - 1.02) > 1e-6) fail(`market-frame forward moved by ${ratio}, expected 1.02`);
  console.log(`market frame forward ${smile0.market.forward.toFixed(4)} -> ${smile1.market.forward.toFixed(4)}`);

  // 3. Re-anchor: the dial returns to 0, the job is narrated, the chart never blanks.
  const [reanchor] = await page.$$(`xpath/.//main//button[starts-with(normalize-space(), "Re-anchor")]`);
  if (!reanchor) throw new Error("the Re-anchor button is missing");
  await reanchor.click();
  let note = null;
  for (let i = 0; i < 40 && !note; i++) {
    note = await page.evaluate(() => document.querySelector('main [role="status"]')?.textContent ?? null);
    if (!note) await sleep(250);
  }
  console.log("re-anchor note:", note);
  if (!note || !/calibrating \d+ node/.test(note)) fail(`unexpected re-anchor note: ${note}`);
  let idle = null;
  for (let i = 0; i < 80; i++) {
    const paths = await page.evaluate(() => document.querySelectorAll("main svg path").length);
    if (paths === 0) fail("the chart went blank during the re-anchor");
    idle = await buttonText(page, /^Re-anchor/);
    if (idle) break;
    await sleep(250);
  }
  if (!idle) fail("the Re-anchor button did not return to idle");
  await sleep(1200); // the epoch-driven view refetch
  const rows2 = await readRows(page);
  const spot2 = await api(page, `/spot/${ticker}`);
  const smile2 = await api(page, `/smiles/${ticker}/${expiry}`);
  console.log("rows (after re-anchor):", rows2, "| backend shift:", spot2.spotReturn, "| stale:", smile2.stale, "hasFit:", smile2.hasFit);
  await shot(page, "spot-3-reanchored.png");
  if (spot2.spotReturn !== 0) fail(`the dial did not reset (${spot2.spotReturn})`);
  if (!smile2.hasFit || smile2.stale) fail(`after the re-anchor: hasFit=${smile2.hasFit} stale=${smile2.stale}`);
  if (!/\s0\.0%/.test(rows2.Scenario ?? "")) fail(`Scenario row after re-anchor: ${rows2.Scenario}`);
  const crashed = await page.evaluate(() => document.body.innerText.includes("hit an error"));
  if (crashed || pageErrors.length) fail(`shell errors: crashed=${crashed} ${pageErrors.join(" | ")}`);
} catch (err) {
  fail(err.message);
} finally {
  await browser.close();
  server.kill();
}
console.log(failures === 0 ? "spot panel check: OK" : `spot panel check: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);

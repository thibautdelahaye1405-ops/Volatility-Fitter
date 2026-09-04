// Headless-Edge check of the Term view's event reading on the LIVE synthetic
// single-origin server (backend/smoke_server.py, throw-away DB):
//   1. before any event the chart draws ONE reading (no "Calendar-day reading"
//      legend, no ladder-spread line);
//   2. Auto-calibrate events (the synthetic ALPHA ladder's front interval runs
//      hotter than the back's log-slope continuation) installs a calendar,
//      the result line reports it, and — on the default Real-time axis — the
//      chart now draws the calendar-day reading dashed beside the working
//      clock's (vol √(w/t) above, the invariant ladder Δw/Δt below) plus the
//      spread readout;
//   3. the same on the Event-dilated axis;
//   4. an empty calendar (PUT) returns the chart to a single reading.
// Screenshots land in .smoke/term-*.png. Prereqs: `npm run build`, Edge, ../.venv.
//   node scripts/term_events_check.mjs
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
// Off the ui_smoke / spot-check ports so all can run. NOT 4190: the WHATWG
// fetch "bad ports" list blocks it (sieve), and Node's fetch obeys the list.
const PORT = 4191;
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
/** Stroke of the calendar-day reading (TermChart.CALENDAR_STROKE). */
const CALENDAR_STROKE = "rgb(251 191 36 / 0.75)";

function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT)], { stdio: ["ignore", "pipe", "pipe"] });
  proc.stderr.on("data", (b) => { const t = String(b); if (/Error|Traceback/.test(t)) console.error(t); });
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 60000;
    proc.on("exit", (code) => reject(new Error(`smoke server exited (${code})`)));
    const probe = async () => {
      try { if ((await fetch(`http://127.0.0.1:${PORT}/universe`)).ok) return resolve(proc); } catch { /* not up */ }
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
const shot = async (page, name) => { try { await page.screenshot({ path: `${OUT}${name}` }); } catch (e) { console.warn(`warn: screenshot ${name}: ${e.message}`); } };
const api = (page, path, init) => page.evaluate(async (p, i) => (await fetch(p, i)).json(), path, init);
const text = (page, sel) => page.evaluate((s) => document.querySelector(s)?.textContent?.trim() ?? null, sel);
/** What the Term chart currently draws: legend entries + dashed calendar paths. */
const readChart = (page, stroke) => page.evaluate((st) => {
  const svg = document.querySelector("main svg.cursor-crosshair");
  const dashed = svg ? Array.from(svg.querySelectorAll(`path[stroke="${st}"]`)).length : -1;
  const legend = Array.from(document.querySelectorAll("main span")).map((e) => e.textContent.trim());
  return { dashed, calendarLegend: legend.includes("Calendar-day reading"), hasSvg: svg !== null };
}, stroke);
/** Wait until the chart is not mid-refresh (the opacity dim) and a condition holds. */
async function waitFor(page, pred, label, ms = 15000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await pred()) return true;
    await sleep(250);
  }
  fail(`timed out waiting for ${label}`);
  return false;
}

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape"); // the first-run Welcome
  await sleep(300);
  await page.click('button[aria-label="Parametric"]');
  await sleep(1500);
  await page.click(`xpath/.//main//button[normalize-space()="Term"]`);
  await waitFor(page, async () => (await readChart(page, CALENDAR_STROKE)).hasSvg, "the Term chart");
  await sleep(800);

  const universe = await api(page, "/universe");
  const ticker = universe.tickers[0];
  await api(page, `/events/${ticker}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ events: [] }) });

  // 1. One reading before any event.
  const before = await readChart(page, CALENDAR_STROKE);
  console.log("before:", before);
  await shot(page, "term-1-before.png");
  if (before.dashed !== 0 || before.calendarLegend) fail(`expected a single reading before events: ${JSON.stringify(before)}`);
  if (await text(page, '[data-testid="ladder-spread"]')) fail("the ladder-spread line should be absent with an empty calendar");

  // 2. Auto-calibrate: result line + both readings on the Real-time axis.
  const [calibrate] = await page.$$(`xpath/.//h3[normalize-space()="Auto-calibrate events"]/following::button[normalize-space()="Calibrate"][1]`);
  if (!calibrate) throw new Error("the Auto-calibrate Calibrate button is missing");
  await calibrate.click();
  await waitFor(page, async () => (await text(page, '[data-testid="autocal-result"]')) !== null, "the auto-calibrate result line");
  const result = await text(page, '[data-testid="autocal-result"]');
  const installed = (await api(page, `/events/${ticker}`)).events;
  console.log("result line:", result, "| installed:", installed);
  if (!/^\d+ events? installed · \d+\.\d extra days$/.test(result ?? "")) fail(`unexpected result line: ${result}`);
  if (installed.length === 0) fail("the synthetic ladder should give the solver at least one peak (front interval)");
  const days = installed.reduce((s, e) => s + e.weight, 0);
  if (!result?.includes(`${installed.length} event`) || !result.includes(`${days.toFixed(1)} extra days`)) fail(`result line ${result} does not match the installed calendar (${installed.length}, ${days.toFixed(1)} d)`);
  await waitFor(page, async () => (await readChart(page, CALENDAR_STROKE)).dashed === 2, "both dashed readings after the refit");
  await sleep(600);
  const after = await readChart(page, CALENDAR_STROKE);
  const spread = await text(page, '[data-testid="ladder-spread"]');
  console.log("after:", after, "| spread:", spread);
  await shot(page, "term-2-after.png");
  if (after.dashed !== 2 || !after.calendarLegend) fail(`expected the dashed calendar vol + ladder on the Real-time axis: ${JSON.stringify(after)}`);
  const m = /calendar (\d+) bp → event time (\d+) bp/.exec(spread ?? "");
  if (!m) fail(`unexpected ladder-spread line: ${spread}`);
  else if (Number(m[2]) > Number(m[1])) fail(`the event-time spread (${m[2]}) should not exceed the calendar one (${m[1]})`);
  // Hover readout carries both readings.
  const svg = await page.$("main svg.cursor-crosshair");
  const box = await svg.boundingBox();
  await page.mouse.move(box.x + box.width * 0.35, box.y + box.height * 0.3);
  await sleep(300);
  const hover = await page.evaluate(() => Array.from(document.querySelectorAll("main div")).map((d) => d.textContent.trim()).find((t) => /^t \d/.test(t)) ?? null);
  console.log("hover:", hover);
  if (!hover || !/\(cal \d/.test(hover) || !/fwd var [\d.]+ \(cal [\d.]+\)/.test(hover)) fail(`hover readout lacks the calendar reading: ${hover}`);
  await page.mouse.move(5, 5);

  // 3. Event-dilated axis keeps both readings.
  await page.click(`xpath/.//main//button[normalize-space()="Event-dilated"]`);
  await sleep(600);
  const dilated = await readChart(page, CALENDAR_STROKE);
  console.log("dilated:", dilated);
  await shot(page, "term-3-dilated.png");
  if (dilated.dashed !== 2 || !dilated.calendarLegend) fail(`expected both readings on the dilated axis: ${JSON.stringify(dilated)}`);
  await page.click(`xpath/.//main//button[normalize-space()="Real time"]`);

  // 4. Empty calendar: back to one reading (the panel edits go through PUT).
  await api(page, `/events/${ticker}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ events: [] }) });
  await page.click(`xpath/.//main//button[normalize-space()="Densities"]`);
  await sleep(500);
  await page.click(`xpath/.//main//button[normalize-space()="Term"]`);
  await waitFor(page, async () => { const c = await readChart(page, CALENDAR_STROKE); return c.hasSvg && c.dashed === 0; }, "a single reading after clearing the calendar");
  const cleared = await readChart(page, CALENDAR_STROKE);
  console.log("cleared:", cleared);
  if (cleared.dashed !== 0 || cleared.calendarLegend) fail(`expected a single reading after clearing: ${JSON.stringify(cleared)}`);

  if (pageErrors.length) fail(`page errors: ${pageErrors.join(" | ")}`);
} finally {
  await browser.close();
  server.kill();
}
console.log(failures === 0 ? "term events check: OK" : `term events check: ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);

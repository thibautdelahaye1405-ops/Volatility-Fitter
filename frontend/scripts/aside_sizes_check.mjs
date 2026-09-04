// Headless-Edge check of the right-hand column's three sizes (lib/asideSizes)
// on the LIVE synthetic single-origin server (backend/smoke_server.py,
// throw-away DB): the Spot move · Variance swap · Fit diagnostics cards all
// sit at the standard size by default, expanding one compresses the other two
// to a single row, folding it back returns all three to standard, the column
// never scrolls at any state (1400×900 and a 1280×720 laptop viewport), and
// the focus carries over to the Local Vol aside. Screenshots of the column
// land in .smoke/aside-*.png. Prereqs: `npm run build`, Edge, ../.venv.
//   node scripts/aside_sizes_check.mjs
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4192; // off the ui_smoke (4188) and spot-check (4189) ports
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const SMOKE_SERVER = winPath(new URL("../../backend/smoke_server.py", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function startLiveServer() {
  const proc = spawn(PY, [SMOKE_SERVER, "--port", String(PORT)], { stdio: ["ignore", "pipe", "pipe"] });
  proc.stdout.on("data", (b) => console.log(String(b).trim()));
  proc.stderr.on("data", (b) => { const t = String(b); if (/Error|Traceback/.test(t)) console.error(t); });
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 180000; // cold Numba caches can take > 60 s
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

/** The column's cards {id: size}, its heights, and whether it scrolls. */
const readColumn = (page) => page.evaluate(() => {
  const aside = document.querySelector("main aside:has([data-aside-panel])");
  if (!aside) return null;
  const sizes = {};
  const heights = {};
  for (const card of aside.querySelectorAll("[data-aside-panel]")) {
    sizes[card.dataset.asidePanel] = card.dataset.asideSize;
    heights[card.dataset.asidePanel] = Math.round(card.getBoundingClientRect().height);
  }
  return { sizes, heights, clientHeight: aside.clientHeight, scrollHeight: aside.scrollHeight, scrolls: aside.scrollHeight > aside.clientHeight + 1 };
});
const shot = async (page, name) => {
  try {
    const aside = await page.$("main aside:has([data-aside-panel])");
    await (aside ?? page).screenshot({ path: `${OUT}${name}` });
  } catch (e) { console.warn(`warn: screenshot ${name}: ${e.message}`); }
};
const clickLabel = async (page, label) => {
  const sel = `button[aria-label="${label}"]`;
  await page.waitForSelector(sel, { timeout: 5000 });
  await page.click(sel);
  await sleep(250);
};
const expectSizes = (label, col, want) => {
  const got = JSON.stringify(col?.sizes ?? null);
  if (got !== JSON.stringify(want)) fail(`${label}: sizes ${got}, expected ${JSON.stringify(want)}`);
  if (col?.scrolls) fail(`${label}: the column scrolls (${col.scrollHeight} > ${col.clientHeight})`);
  console.log(`${label}: ${got} heights ${JSON.stringify(col?.heights)} column ${col?.scrollHeight}/${col?.clientHeight}${col?.scrolls ? " SCROLLS" : ""}`);
};
const M = { spot: "M", varswap: "M", diag: "M" };

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
  await page.waitForSelector("main aside [data-aside-panel]", { timeout: 15000 });
  await sleep(1200);

  // 1. Default: all three standard, nothing scrolls.
  expectSizes("parametric default", await readColumn(page), M);
  await shot(page, "aside-1-standard.png");

  // 2. Expand each card in turn: it goes L, the other two S; the compact row expands the next.
  await clickLabel(page, "Expand Variance swap");
  expectSizes("varswap expanded", await readColumn(page), { spot: "S", varswap: "L", diag: "S" });
  await shot(page, "aside-2-varswap.png");
  await clickLabel(page, "Expand Fit diagnostics");
  expectSizes("diagnostics expanded", await readColumn(page), { spot: "S", varswap: "S", diag: "L" });
  await shot(page, "aside-3-diagnostics.png");
  await clickLabel(page, "Expand Spot move");
  expectSizes("spot expanded", await readColumn(page), { spot: "L", varswap: "S", diag: "S" });
  await shot(page, "aside-4-spot.png");

  // 3. The focus is shared with the Local Vol aside, and folds back there.
  await page.click('button[aria-label="Local Vol"]');
  await page.waitForSelector("main aside [data-aside-panel]", { timeout: 15000 });
  await sleep(1200);
  const lv = await readColumn(page);
  if (lv?.sizes?.spot !== "L") fail(`Local Vol aside should inherit the expanded Spot card: ${JSON.stringify(lv?.sizes)}`);
  if (lv?.scrolls) fail("Local Vol column scrolls with Spot expanded");
  await shot(page, "aside-5-localvol-spot.png");
  await clickLabel(page, "Shrink Spot move");
  const lvM = await readColumn(page);
  if (lvM?.sizes?.spot !== "M" || lvM?.sizes?.diag !== "M") fail(`fold back should return the LV cards to standard: ${JSON.stringify(lvM?.sizes)}`);
  if (lvM?.scrolls) fail("Local Vol column scrolls at the standard size");
  console.log(`local vol standard: ${JSON.stringify(lvM?.sizes)} heights ${JSON.stringify(lvM?.heights)} column ${lvM?.scrollHeight}/${lvM?.clientHeight}`);
  await shot(page, "aside-6-localvol-standard.png");
  await clickLabel(page, "Expand Fit diagnostics");
  const lvD = await readColumn(page);
  if (lvD?.sizes?.diag !== "L") fail(`LV diagnostics should expand: ${JSON.stringify(lvD?.sizes)}`);
  if (lvD?.scrolls) fail("Local Vol column scrolls with diagnostics expanded");
  await shot(page, "aside-7-localvol-diagnostics.png");
  await clickLabel(page, "Shrink Fit diagnostics");

  // 4. Laptop viewport: the standard column still fits (the diagnostics card
  //    gives up height first), and so does every expanded state.
  await page.click('button[aria-label="Parametric"]');
  await page.waitForSelector("main aside [data-aside-panel]", { timeout: 15000 });
  await page.setViewport({ width: 1280, height: 720 });
  await sleep(800);
  expectSizes("laptop standard", await readColumn(page), M);
  await shot(page, "aside-8-laptop-standard.png");
  for (const [label, want] of [
    ["Expand Spot move", { spot: "L", varswap: "S", diag: "S" }],
    ["Expand Variance swap", { spot: "S", varswap: "L", diag: "S" }],
    ["Expand Fit diagnostics", { spot: "S", varswap: "S", diag: "L" }],
  ]) {
    await clickLabel(page, label);
    expectSizes(`laptop ${label}`, await readColumn(page), want);
  }
  await shot(page, "aside-9-laptop-diagnostics.png");
  await clickLabel(page, "Shrink Fit diagnostics");
  expectSizes("laptop folded back", await readColumn(page), M);

  if (pageErrors.length) fail(`page errors: ${pageErrors.join(" | ")}`);
} finally {
  await browser.close();
  server.kill();
}
console.log(failures ? `${failures} failure(s)` : "aside sizes check: OK");
process.exit(failures ? 1 : 0);

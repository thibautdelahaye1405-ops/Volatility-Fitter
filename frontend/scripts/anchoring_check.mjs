// Headless-Edge LIVE check of the ANCHORING AXIS (2026-09-07) on the synthetic
// single-origin smoke server (backend/smoke_server.py, throw-away DB):
//   1. through the API: read every node of the first ticker (bootstraps the
//      fits), then SAVE ONE NODE's prior through the per-node route — no
//      Fetch (one prior per node, active on save): the node now has a prior
//      cell that IS production ("+ Prior" tagged prod), and the Graph
//      lattice starts from it (priorSource active_transported), so "Free" is
//      the shadow to ask;
//   2. Parametric → Compare: light the Free chip, expect a shadow table row
//      (data-shadow="free") and a measured Pull on the plain row;
//   3. Parametric → Smile: the Fit switch ([data-fit-anchoring]) shows
//      Production / Free; pick Free, expect the "SHADOW · free" tag and a
//      payload drawn in that cell; Density keeps the choice; Production
//      again clears the tag.
// Port 4192 — NOT 4190 (the WHATWG fetch bad-ports list, obeyed by Node's
// fetch). Screenshots in .smoke/anchoring-*.png. Prereqs: npm run build,
// Edge, ../.venv (the smoke's own prerequisites).
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4192;
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

async function api(method, path) {
  const r = await fetch(`${BASE}${path}`, { method });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`);
  return r.json();
}

/** The first `main` button whose text starts with `label` (chips, switches). */
async function clickMainButton(page, label, scope = "main") {
  const [btn] = await page.$$(`xpath/.//${scope}//button[starts-with(normalize-space(), "${label}")]`);
  if (!btn) throw new Error(`button "${label}" not found in ${scope}`);
  await btn.click();
  await sleep(250);
}

async function clickAria(page, label) {
  const btn = await page.$(`button[aria-label="${label}"]`);
  if (!btn) throw new Error(`button[aria-label="${label}"] not found`);
  await btn.click();
  await sleep(700);
}

async function waitFor(page, fn, what, ms = 15000) {
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

try {
  // 1. Priors through the API: fits first (ungated smoke server), then save + fetch.
  const universe = await api("GET", "/universe");
  const ticker = universe.tickers[0];
  const expiries = universe.expiries[ticker].map((e) => e.expiry);
  for (const e of expiries) await api("GET", `/smiles/${ticker}/${e}`);
  const node = expiries[Math.min(2, expiries.length - 1)];
  const saved = await api("POST", `/smiles/${ticker}/${node}/prior`); // ONE node, no Fetch
  const smile = await api("GET", `/smiles/${ticker}/${node}`);
  console.log(`per-node save: ${JSON.stringify(saved)} · priors status ${JSON.stringify((await api("GET", "/priors")).tickers[0]).slice(0, 160)}`);
  console.log(`axis on ${ticker} ${node}: ${JSON.stringify(smile.anchoring)}`);
  if (!smile.anchoring || smile.anchoring.production !== "prior") throw new Error("the prior cell is not production right after a per-node save");
  if (!smile.priorTransported) throw new Error("the dotted transported prior is not drawn after the save");
  const lattice = (await api("GET", "/graph/nodes")).nodes.filter((n) => n.ticker === ticker);
  const src = Object.fromEntries(lattice.map((n) => [n.expiry, n.priorSource]));
  console.log(`graph lattice prior sources: ${JSON.stringify(src)}`);
  if (src[node] !== "active_transported") throw new Error(`the Graph does not start from the saved node (${src[node]})`);

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape"); // the first-run Welcome
  await sleep(400);
  await clickAria(page, "Parametric");
  // Open the node the API prepared (nodes pane row = its expiry label is
  // formatted; the auto-opened tab is the ticker's mid-ladder node, which is
  // what index 2 of a 4-rung ladder is on the synthetic universe).

  // 2. Compare: Free is the shadow (Prior is production).
  await step("compare-free-shadow-row", async () => {
    await clickMainButton(page, "Compare");
    await waitFor(page, () => !!document.querySelector('main button[aria-pressed][disabled]'), "the Compare chips");
    const prod = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main button[aria-pressed]")).map((b) => b.textContent ?? "").find((t) => /prod/i.test(t)) ?? null);
    if (!prod || !/Prior/.test(prod)) throw new Error(`the prod tag is not on + Prior: ${prod}`);
    await clickMainButton(page, "Free");
    await waitFor(page, () => !!document.querySelector('main tr[data-shadow="free"]'), "the Free shadow row");
    const pull = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll("main tbody tr"));
      return rows.map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent?.trim() ?? ""));
    });
    console.log(`     rows: ${pull.map((r) => `${r[0]} pull=${r[8]}`).join(" | ")}`);
    if (pull.length < 2 || pull.every((r) => r[8] === "—")) throw new Error("no measured pull in the table");
    const legend = await page.evaluate(() => document.querySelector("main")?.innerText.includes("LQD · free"));
    if (!legend) throw new Error("the shadow series label is missing from the chart");
    await page.screenshot({ path: `${OUT}anchoring-compare.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  // 3. Smile: the Fit switch draws the Free shadow; Density keeps it; Production clears it.
  await step("smile-fit-switch-free", async () => {
    await clickMainButton(page, "Smile");
    await waitFor(page, () => !!document.querySelector("main [data-fit-anchoring]"), "the Fit switch");
    const opts = await page.evaluate(() => Array.from(document.querySelectorAll("main [data-fit-anchoring] button")).map((b) => b.textContent));
    console.log(`     fit switch: ${opts.join(" / ")}`);
    if (!opts.includes("Free") || opts.includes("+ Prior")) throw new Error(`unexpected switch options ${opts}`);
    await clickMainButton(page, "Free", 'main//*[@data-fit-anchoring]');
    await waitFor(page, () => document.querySelector("main")?.innerText.includes("SHADOW · free") ?? false, "the SHADOW tag");
    await sleep(400);
    await page.screenshot({ path: `${OUT}anchoring-smile-free.png` });
    await clickMainButton(page, "Density");
    await waitFor(page, () => document.querySelector('main [data-fit-anchoring="free"]') !== null, "the Density view keeping Free");
    await sleep(800);
    await page.screenshot({ path: `${OUT}anchoring-density-free.png` });
    await clickMainButton(page, "Smile");
    await clickMainButton(page, "Production", 'main//*[@data-fit-anchoring]');
    await waitFor(page, () => !(document.querySelector("main")?.innerText.includes("SHADOW ·") ?? true), "the tag to clear");
    await page.screenshot({ path: `${OUT}anchoring-smile-production.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });
} finally {
  await browser.close();
  server.kill();
}
if (failures > 0) { console.error(`${failures} step(s) failed`); process.exit(1); }
console.log("anchoring axis: Compare shadow row + pull, Fit switch Smile/Density (screenshots in .smoke/anchoring-*.png)");

// Headless-Edge LIVE check of the GRAPH-INFERRED smile (2026-09-07) on the
// synthetic single-origin smoke server (backend/smoke_server.py):
//   1. through the API: bootstrap every node's fit, darken the mid-ladder
//      node (the one the workbench auto-opens), Save + Fetch priors so the
//      Run has a baseline, then POST /graph/extrapolate (the Run);
//   2. Parametric → Smile on that node: the INFERRED · GRAPH badge, the
//      "Inferred from graph · run …" legend entry and the violet dash-dot
//      path must render; the Graph layer-rail toggle hides and shows them.
// Port 4193 (never 4190 — the WHATWG fetch bad-ports list). Screenshots in
// .smoke/inferred-*.png. Prereqs: npm run build, Edge, ../.venv.
import { existsSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4193;
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
  const universe = await api("GET", "/universe");
  const ticker = universe.tickers[0];
  const expiries = universe.expiries[ticker].map((e) => e.expiry);
  for (const e of expiries) await api("GET", `/smiles/${ticker}/${e}`);
  const node = expiries[Math.min(2, expiries.length - 1)];
  await api("PUT", `/universe/lit/${ticker}/${node}`, { lit: false });
  await api("POST", "/priors/save-all");
  const run = await api("POST", "/graph/extrapolate", {});
  const solved = run.nodes.find((n) => n.ticker === ticker && n.expiry === node);
  console.log(`run: ${run.nodes.length} nodes · dark ${ticker} ${node}: ${JSON.stringify(solved && { lit: solved.lit, post: solved.postAtmVol, source: solved.priorSource })}`);
  const smile = await api("GET", `/smiles/${ticker}/${node}`);
  const gi = smile.graphInferred;
  console.log(`payload: graphInferred ${gi ? `${gi.curve.length} pts · run ${gi.runTs} · ${gi.priorSource} · ATM ${gi.postAtmVol.toFixed(4)} ± ${gi.sd.toFixed(4)}` : "NONE"} · market.inferred ${smile.market?.inferred?.length ?? 0} pts`);
  if (!gi) throw new Error("no inferred smile on the dark node after the Run");

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2500);
  await page.keyboard.press("Escape");
  await sleep(400);
  const lens = await page.$('button[aria-label="Parametric"]');
  if (!lens) throw new Error("Parametric lens button not found");
  await lens.click();
  await sleep(1500);

  await step("inferred-smile-drawn", async () => {
    await waitFor(page, () => (document.querySelector("main h2")?.textContent ?? "").length > 0, "the node title");
    const title = await page.evaluate(() => document.querySelector("main h2")?.textContent);
    console.log(`     node on screen: ${title}`);
    await waitFor(page, () => document.querySelector("main")?.innerText.includes("INFERRED · GRAPH") ?? false, "the INFERRED · GRAPH badge");
    const legend = await page.evaluate(() => document.querySelector("main")?.innerText.includes("Inferred from graph"));
    if (!legend) throw new Error("the legend entry is missing");
    const dashed = await page.evaluate(() => document.querySelectorAll('main svg path[stroke-dasharray="8 3 2 3"]').length);
    if (dashed < 1) throw new Error("the violet dash-dot path is missing");
    await page.screenshot({ path: `${OUT}inferred-smile.png` });
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });

  await step("graph-layer-toggle", async () => {
    const btn = await page.$('[aria-label="Chart layers"] button[aria-label="Graph"]');
    if (!btn) throw new Error("the Graph layer-rail toggle is missing");
    await btn.click();
    await waitFor(page, () => !(document.querySelector("main")?.innerText.includes("INFERRED · GRAPH") ?? true), "the badge to hide");
    const dashed = await page.evaluate(() => document.querySelectorAll('main svg path[stroke-dasharray="8 3 2 3"]').length);
    if (dashed !== 0) throw new Error("the inferred path is still drawn with the layer off");
    await page.screenshot({ path: `${OUT}inferred-smile-hidden.png` });
    await btn.click();
    await waitFor(page, () => document.querySelector("main")?.innerText.includes("INFERRED · GRAPH") ?? false, "the badge to come back");
    if (pageErrors.length) throw new Error(pageErrors.join("; "));
  });
} finally {
  await browser.close();
  server.kill();
}
if (failures > 0) { console.error(`${failures} step(s) failed`); process.exit(1); }
console.log("graph-inferred smile: badge + legend + dash-dot path on the dark node, layer toggle (screenshots in .smoke/inferred-*.png)");

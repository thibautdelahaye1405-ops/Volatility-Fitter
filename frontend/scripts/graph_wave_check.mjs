// One-off wave-cinematics check (not part of CI): single lit node + manual
// shift, catch the BFS-staged reveal mid-flight. Usage: node scripts/graph_wave_check.mjs [port]
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = process.argv[2] ?? "8011";
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");

// Darken every node except SPY's front expiry so the wave has distance to travel.
const nodesRes = await fetch(`http://localhost:${PORT}/graph/nodes`);
const { nodes } = await nodesRes.json();
let keep = null;
for (const n of nodes) {
  const lit = keep === null && n.ticker === "SPY";
  if (lit) keep = `${n.ticker}|${n.expiry}`;
  await fetch(
    `http://localhost:${PORT}/universe/lit/${n.ticker}/${encodeURIComponent(n.expiry)}`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lit }) },
  );
}
console.log(`lit anchor: ${keep}; ${nodes.length - 1} nodes darkened`);

mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"],
});
let failed = false;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 950 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 45000 });
  const [graphTab] = await page.$$('xpath/.//nav//button[normalize-space()="Graph"]');
  await graphTab.click();
  await page.waitForFunction(
    () => document.querySelectorAll("main svg circle").length > 5,
    { timeout: 120000 },
  );

  const [manualBtn] = await page.$$('xpath/.//button[normalize-space()="Manual what-if"]');
  await manualBtn.click();
  await new Promise((r) => setTimeout(r, 400));

  // The single lit node's shift input (step 0.5 is unique to observation rows).
  await page.evaluate(() => {
    const el = document.querySelector('aside input[step="0.5"]');
    if (!el) throw new Error("shift input not found");
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(el, "2");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 200));

  const [propagateBtn] = await page.$$('xpath/.//button[normalize-space()="Propagate"]');
  await propagateBtn.click();
  // Results land, wave starts: catch it ~2 hops in (160ms/hop).
  await page.waitForFunction(
    () => [...document.querySelectorAll("button")].some(
      (b) => b.textContent?.trim() === "Propagate" && !b.disabled),
    { timeout: 60000 },
  );
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: `${OUT}graph-wave-mid.png` });
  await new Promise((r) => setTimeout(r, 2500));
  await page.screenshot({ path: `${OUT}graph-wave-done.png` });

  if (pageErrors.length > 0) {
    failed = true;
    pageErrors.forEach((e) => console.error(`pageerror: ${e}`));
  }
} finally {
  await browser.close();
}
console.log(failed ? "wave check: FAILED" : "wave check: ok");
process.exit(failed ? 1 : 0);

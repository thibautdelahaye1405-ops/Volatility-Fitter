// One-off visual check of the Graph network view against a LIVE backend.
// Usage: node scripts/graph_visual.mjs [port]   (default 8011)
// Drives headless Edge: open the app, go to Graph, wait for the baseline
// fit, screenshot; then Solve (sandbox) and screenshot the posterior field.
// Screenshots land in .smoke/graph-live-*.png. Exits 1 on page errors.
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = process.argv[2] ?? "8011";
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");

mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: true,
  args: ["--no-first-run", "--disable-gpu"],
});
let failed = false;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 950 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 45000 });
  const [graphTab] = await page.$$('xpath/.//nav//button[normalize-space()="Graph"]');
  if (!graphTab) throw new Error("Graph nav button not found");
  await graphTab.click();

  // Wait for the baseline fit: node circles appear inside the chart svg.
  try {
    await page.waitForFunction(
      () => document.querySelectorAll("main svg circle").length > 5,
      { timeout: 120000 },
    );
  } catch (err) {
    await page.screenshot({ path: `${OUT}graph-live-stuck.png` });
    const text = await page.evaluate(() => document.querySelector("main")?.innerText ?? "(no main)");
    console.error(`STUCK — main text:\n${text.slice(0, 600)}`);
    throw err;
  }
  await new Promise((r) => setTimeout(r, 800)); // settle the fit transform
  await page.screenshot({ path: `${OUT}graph-live-baseline.png` });

  // Propagate (default source: from calibrations) and shoot the posterior.
  const [propagateBtn] = await page.$$('xpath/.//button[normalize-space()="Propagate"]');
  if (propagateBtn) {
    const disabled = await propagateBtn.evaluate((b) => b.disabled);
    if (!disabled) {
      await propagateBtn.click();
      await page.waitForFunction(
        () =>
          [...document.querySelectorAll("button")].some(
            (b) => b.textContent?.trim() === "Propagate" && !b.disabled,
          ),
        { timeout: 120000 },
      );
      await new Promise((r) => setTimeout(r, 1200));
      await page.screenshot({ path: `${OUT}graph-live-solved.png` });
    } else console.log("Propagate disabled — baseline shot only");
  } else console.log("Propagate button not found — baseline shot only");

  if (pageErrors.length > 0) {
    failed = true;
    pageErrors.forEach((e) => console.error(`pageerror: ${e}`));
  }
} finally {
  await browser.close();
}
console.log(failed ? "graph visual: FAILED" : "graph visual: ok (see .smoke/graph-live-*.png)");
process.exit(failed ? 1 : 0);

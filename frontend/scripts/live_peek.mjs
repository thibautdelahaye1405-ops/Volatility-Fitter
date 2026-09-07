// Read-only peek at the RUNNING app (vite dev :5173 -> backend :8000): open
// the Parametric lens, the Compare sub-view, dump the chip strip + table text
// and screenshot .smoke/peek-*.png. Never edits, calibrates or saves anything
// (the Compare fits are the endpoint's own side cache — read-only by doctrine).
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const URL_ = process.argv[2] ?? "http://localhost:5173/";
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  await page.goto(URL_, { waitUntil: "networkidle2", timeout: 60000 });
  await sleep(3000);
  await page.keyboard.press("Escape");
  await sleep(300);
  const lens = await page.$('button[aria-label="Parametric"]');
  if (lens) { await lens.click(); await sleep(1500); }
  await page.screenshot({ path: `${OUT}peek-smile.png` });
  const [sub] = await page.$$('xpath/.//main//button[normalize-space()="Compare"]');
  if (sub) { await sub.click(); await sleep(6000); }
  await page.screenshot({ path: `${OUT}peek-compare.png` });
  const chips = await page.evaluate(() =>
    Array.from(document.querySelectorAll("main button[aria-pressed]")).map((b) =>
      `${b.textContent?.trim()} [pressed=${b.getAttribute("aria-pressed")} disabled=${b.disabled}]`));
  const rows = await page.evaluate(() =>
    Array.from(document.querySelectorAll("main tbody tr")).map((r) => r.textContent?.replace(/\s+/g, " ").trim()));
  const title = await page.evaluate(() => document.querySelector("main h2")?.textContent);
  console.log("node:", title);
  console.log("chips:", chips.join(" | "));
  console.log("rows:", rows.join(" || "));
  console.log("errors:", errors.length ? errors.join("\n") : "none");
} finally {
  await browser.close();
}

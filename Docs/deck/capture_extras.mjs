// Retake edge_editor (with seeded edges) + options_calibration_crop (bounded clip).
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.argv[2] ?? "http://127.0.0.1:8001";
const SHOTS = "C:\\Users\\thiba\\vol-fitter\\Docs\\deck\\assets\\shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickText(page, text) {
  const ok = await page.evaluate((t) => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === t);
    if (!b) return false;
    b.click();
    return true;
  }, text);
  if (!ok) throw new Error(`button "${text}" not found`);
  await sleep(700);
}

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--force-color-profile=srgb", "--hide-scrollbars", "--window-size=1920,1080"] });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 2 });
await page.evaluateOnNewDocument(() => {
  localStorage.setItem("volfit.viewSettings", JSON.stringify({ scheme: "light", contrast: 1, brightness: 1 }));
});
// Persist a representative block rule so the editor shows a desk-authored
// graph (weights + betas) instead of the empty-overrides auto-lattice state.
const rule = {
  rule: {
    pairs: [
      { a: "SPY", b: "QQQ", weight: 30, beta: 1.0, symmetric: true },
      { a: "SPY", b: "IWM", weight: 30, beta: 0.9, symmetric: true },
      { a: "SPY", b: "AAPL", weight: 30, beta: 1.0, symmetric: true },
      { a: "QQQ", b: "NVDA", weight: 30, beta: 1.3, symmetric: true },
      { a: "QQQ", b: "AAPL", weight: 30, beta: 1.1, symmetric: true },
    ],
    calendar: [
      { ticker: "SPY", weight: 100, beta: 1.0 },
      { ticker: "QQQ", weight: 100, beta: 1.0 },
      { ticker: "AAPL", weight: 100, beta: 1.0 },
      { ticker: "NVDA", weight: 100, beta: 1.0 },
      { ticker: "IWM", weight: 100, beta: 1.0 },
    ],
    overrides: [],
  },
};
const res = await fetch(BASE + "/graph/edges/blocks", {
  method: "PUT",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(rule.rule),
});
if (!res.ok) throw new Error("PUT /graph/edges/blocks failed: " + res.status + " " + (await res.text()));
console.log("block rule persisted:", JSON.stringify(await res.json()).slice(0, 120));

await page.goto(BASE + "/", { waitUntil: "networkidle2", timeout: 120000 });
await page.waitForFunction(() => !!document.querySelector('nav[aria-label="Workspaces"]'), { timeout: 60000 });
await page.evaluate(() => document.fonts.ready);

// ---- Graph tab: propagate, then open the edge editor and ensure edges exist
await page.evaluate(() => {
  [...document.querySelectorAll('nav[aria-label="Workspaces"] button')].find((b) => b.textContent.trim() === "Graph")?.click();
});
await sleep(1500);
await clickText(page, "Propagate");
await sleep(8000); // wave animation settles
await clickText(page, "Edges");
await sleep(1200);
await page.waitForFunction(() => {
  const el = [...document.querySelectorAll("span,div")].find((x) => /^\d+ edges$/.test(x.textContent.trim()));
  return el && parseInt(el.textContent) > 0;
}, { timeout: 20000 });
const edges = await page.evaluate(() => {
  const el = [...document.querySelectorAll("span,div")].find((x) => /^\d+ edges$/.test(x.textContent.trim()));
  return parseInt(el.textContent);
});
console.log("edge badge:", edges, "edges");
await sleep(800);
// clip the modal (h3 "Edge weights" container)
const modalRect = await page.evaluate(() => {
  const h = [...document.querySelectorAll("h3")].find((x) => x.textContent.trim().startsWith("Edge weights"));
  if (!h) return null;
  let el = h;
  for (let i = 0; i < 8 && el.parentElement; i++) {
    el = el.parentElement;
    const r = el.getBoundingClientRect();
    if (r.width > 700 && r.height > 300) break;
  }
  const r = el.getBoundingClientRect();
  return { x: Math.max(0, r.x - 4), y: Math.max(0, r.y - 4), width: Math.min(1920, r.width + 8), height: Math.min(1080, r.height + 8) };
});
if (!modalRect) throw new Error("edge modal not found");
await page.screenshot({ path: SHOTS + "\\edge_editor.png", clip: modalRect });
console.log("SHOT edge_editor.png", JSON.stringify(modalRect));
await page.evaluate(() => document.querySelector('button[title="Close"]')?.click());
await sleep(700);

// ---- Options tab: bounded clip of the Calibration card
await page.evaluate(() => {
  [...document.querySelectorAll('nav[aria-label="Workspaces"] button')].find((b) => b.textContent.trim() === "Options")?.click();
});
await sleep(1500);
const cardRect = await page.evaluate(() => {
  const h = [...document.querySelectorAll("h3")].find((x) => x.textContent.trim() === "Calibration");
  if (!h) return null;
  h.scrollIntoView({ block: "start" });
  return true;
});
if (!cardRect) throw new Error("Calibration card not found");
await sleep(900);
const clip = await page.evaluate(() => {
  const h = [...document.querySelectorAll("h3")].find((x) => x.textContent.trim() === "Calibration");
  const card = h.closest('[class*="rounded"]') ?? h.parentElement;
  const r = card.getBoundingClientRect();
  const height = Math.min(r.height, 1040, 1080 - Math.max(0, r.y));
  return { x: Math.max(0, r.x - 2), y: Math.max(0, r.y - 2), width: Math.min(1918, r.width + 4), height: Math.max(300, height) };
});
await page.screenshot({ path: SHOTS + "\\options_calibration_crop.png", clip });
console.log("SHOT options_calibration_crop.png", JSON.stringify(clip));
await browser.close();
console.log("RETAKES DONE");

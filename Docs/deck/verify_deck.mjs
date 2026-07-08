// Screenshot every slide of the built deck for visual verification.
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const DECK = "C:\\Users\\thiba\\vol-fitter\\Docs\\deck\\volfitter_deck.html";
const OUT = process.argv[2] ?? "C:\\Users\\thiba\\AppData\\Local\\Temp\\claude\\C--Users-thiba-vol-fitter\\58e790b8-d813-4578-9916-b05e2b73bee8\\scratchpad\\deckverify";

fs.mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--window-size=1920,1080"] });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
await page.goto("file:///" + DECK.replace(/\\/g, "/"), { waitUntil: "networkidle2", timeout: 120000 });
await page.evaluate(() => document.fonts.ready);
const n = await page.evaluate(() => document.querySelectorAll(".slide").length);
console.log(`slides: ${n}`);
for (let i = 0; i < n; i++) {
  await page.evaluate((i) => {
    const slides = [...document.querySelectorAll(".slide")];
    slides.forEach((el, j) => el.classList.toggle("active", j === i));
  }, i);
  await new Promise((r) => setTimeout(r, 250));
  await page.screenshot({ path: path.join(OUT, `slide-${String(i + 1).padStart(2, "0")}.png`) });
  // overflow check: content past the slide bottom, or clipped inside .cols
  const overflow = await page.evaluate(() => {
    const s = document.querySelector(".slide.active");
    const rect = s.getBoundingClientRect();
    const scale = rect.height / 1080;
    const msgs = [];
    let worst = 0, worstEl = "";
    for (const el of s.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      const bottomInSlide = (r.bottom - rect.top) / scale;
      if (bottomInSlide > 1080 + 1 && r.height > 0 && bottomInSlide > worst) {
        worst = bottomInSlide; worstEl = el.className?.toString?.().slice(0, 40) || el.tagName;
      }
    }
    if (worst) msgs.push(`${Math.round(worst - 1080)}px past bottom (${worstEl})`);
    for (const cols of s.querySelectorAll(".cols")) {
      const cr = cols.getBoundingClientRect();
      let clip = 0, clipEl = "";
      for (const el of cols.querySelectorAll("p,li,div.stat,div.shotcap,ul,table")) {
        const r = el.getBoundingClientRect();
        const over = (r.bottom - cr.bottom) / scale;
        if (over > 4 && r.height > 0 && over > clip) { clip = over; clipEl = (el.className?.toString?.().slice(0, 30) || el.tagName) + ": " + el.textContent.trim().slice(0, 40); }
      }
      if (clip > 0) msgs.push(`CLIPPED ${Math.round(clip)}px in .cols (${clipEl})`);
    }
    return msgs.join(" · ");
  });
  console.log(`slide ${i + 1}: ${overflow || "ok"}`);
}
await browser.close();
console.log("DONE " + OUT);

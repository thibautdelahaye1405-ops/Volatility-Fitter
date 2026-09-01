// One-off live probe of Ask @Vol-Fitter's Claude tier through the REAL UI
// (HELP CENTER ARC): drives headless Edge against a single-origin server whose
// process has VOLFIT_ANTHROPIC_KEY, opens the Ask page (Ctrl+Shift+/), asks a
// question, waits for the streamed answer and prints the tier label, the
// answer text and a screenshot path. Not part of the smoke (spends money).
//
//   node scripts/ask_claude_probe.mjs http://localhost:4189 "your question"
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const [base = "http://localhost:4189", question = "How do I exclude a quote from the fit and undo it?"] = process.argv.slice(2);
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${base}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(2000);
  await page.keyboard.press("Escape"); // the first-run Welcome
  await sleep(300);
  await page.keyboard.down("Control"); await page.keyboard.down("Shift"); await page.keyboard.press("Slash");
  await page.keyboard.up("Shift"); await page.keyboard.up("Control");
  await sleep(1200); // /help/ask/status round trip
  const banner = await page.evaluate(() => document.querySelector('[data-help-page="ask"] .rounded-md')?.textContent ?? "");
  console.log(`banner: ${banner.trim()}`);
  if (!/Claude/.test(banner)) throw new Error("the Ask panel does not report the Claude tier");
  await page.type('input[aria-label="Ask a question"]', question);
  await page.keyboard.press("Enter");
  // Wait for the streamed answer to finish (the busy dot disappears, text present).
  let answer = "";
  for (let i = 0; i < 90; i++) {
    await sleep(1000);
    const state = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('[data-help-page="ask"] .help-md'));
      const last = cards[cards.length - 1];
      const busy = document.querySelector('[data-help-page="ask"] .animate-pulse') !== null;
      const label = Array.from(document.querySelectorAll('[data-help-page="ask"] .uppercase')).map((e) => e.textContent).join(" | ");
      return { text: last?.textContent ?? "", busy, label };
    });
    if (state.text && !state.busy) { answer = state.text; console.log(`labels: ${state.label}`); break; }
  }
  const shot = `${OUT}ask-claude-live.png`;
  await page.screenshot({ path: shot });
  if (!answer) throw new Error("no streamed answer within 90 s");
  console.log(`answer (${answer.length} chars):\n${answer}\n\nscreenshot: ${shot}`);
  if (errors.length) { console.error("page errors:", errors); process.exitCode = 1; }
} finally {
  await browser.close();
}

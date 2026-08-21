// Headless-Edge XHR recorder for venue pages (market-data adapter research).
//
//   node scripts/capture_xhr.mjs <url> <out-prefix> [--wait ms] [--click css]... [--type css=text]... [--scroll]
//
// Opens <url> in headless Edge (puppeteer-core, the UI-smoke browser), optionally
// clicks / types into selectors (one --click / --type per action, in order), waits,
// and records every network response of an XHR/fetch/document/script/other that
// carries JSON / XML / text: <out-prefix>.jsonl gets one line per response (url,
// status, method, request headers subset, postData, content-type, size, a 600-char
// body preview), and bodies > 2 kB are saved whole as <out-prefix>.<n>.body.
// Purely read-only research tooling — no repo code depends on it.
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const [url, prefix, ...rest] = process.argv.slice(2);
if (!url || !prefix) {
  console.error("usage: node scripts/capture_xhr.mjs <url> <out-prefix> [--wait ms] [--click css]... [--type css=text]... [--scroll]");
  process.exit(2);
}
let wait = 12000;
const actions = [];
let scroll = false;
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--wait") wait = Number(rest[++i]);
  else if (rest[i] === "--click") actions.push({ click: rest[++i] });
  else if (rest[i] === "--type") { const [css, ...t] = rest[++i].split("="); actions.push({ type: css, text: t.join("=") }); }
  else if (rest[i] === "--scroll") scroll = true;
}

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--window-size=1400,1000", "--lang=en-US"],
});
const page = await browser.newPage();
await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0");
await page.setViewport({ width: 1400, height: 1000 });
const out = fs.createWriteStream(`${prefix}.jsonl`, { flags: "w" });
let n = 0;
const KEEP = /json|xml|text\/plain|javascript|html/i;
page.on("response", async (res) => {
  try {
    const req = res.request();
    const type = req.resourceType();
    const ct = res.headers()["content-type"] || "";
    if (!["xhr", "fetch", "document", "other", "script"].includes(type)) return;
    if (!KEEP.test(ct)) return;
    let body = "";
    try { body = await res.text(); } catch { body = ""; }
    const idx = ++n;
    const hdrs = req.headers();
    const keep = {};
    for (const k of Object.keys(hdrs)) if (/^(x-|authorization|referer|origin|accept$|content-type|cookie)/i.test(k)) keep[k] = k.toLowerCase() === "cookie" ? `<${hdrs[k].length} chars>` : hdrs[k];
    const line = {
      i: idx, type, method: req.method(), url: res.url(), status: res.status(), ct, size: body.length,
      reqHeaders: keep, postData: req.postData() || null, preview: body.slice(0, 600),
    };
    out.write(JSON.stringify(line) + "\n");
    if (body.length > 2048) fs.writeFileSync(`${prefix}.${idx}.body`, body);
  } catch { /* ignore */ }
});
try {
  await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
} catch (e) {
  console.error("goto:", String(e).slice(0, 200));
}
for (const a of actions) {
  try {
    if (a.click) { await page.waitForSelector(a.click, { timeout: 15000 }); await page.click(a.click); }
    if (a.type) { await page.waitForSelector(a.type, { timeout: 15000 }); await page.type(a.type, a.text); }
    await new Promise((r) => setTimeout(r, 2500));
  } catch (e) {
    console.error("action failed:", JSON.stringify(a), String(e).slice(0, 160));
  }
}
if (scroll) {
  for (let y = 0; y < 6000; y += 800) { await page.evaluate((yy) => window.scrollTo(0, yy), y); await new Promise((r) => setTimeout(r, 400)); }
}
await new Promise((r) => setTimeout(r, wait));
const title = await page.title();
console.log(`captured ${n} responses from ${url} (title: ${title})`);
out.end();
await browser.close();

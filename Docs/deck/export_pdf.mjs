// Export the built deck to PDF (one 1920x1080 page per slide, print CSS).
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const DECK = "C:\\Users\\thiba\\vol-fitter\\Docs\\deck\\volfitter_deck.html";
const OUT = "C:\\Users\\thiba\\vol-fitter\\Docs\\deck\\volfitter_deck.pdf";

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true });
const page = await browser.newPage();
await page.goto("file:///" + DECK.replace(/\\/g, "/"), { waitUntil: "networkidle2", timeout: 180000 });
await page.evaluate(() => document.fonts.ready);
await new Promise((r) => setTimeout(r, 1500));
await page.pdf({ path: OUT, width: "1920px", height: "1080px", printBackground: true, timeout: 600000 });
await browser.close();
console.log("PDF written: " + OUT);

// Deck screenshot capture — the SPY 3D triangulated Local-Vol surface only.
//
// Run from frontend\ (puppeteer-core resolves from the script's dir; shots
// land in frontend\assets\shots — copy back to Docs\deck\assets\shots):
//     Copy-Item Docs\deck\capture_lv3d.mjs frontend\; cd frontend; node .\capture_lv3d.mjs
//
// Assumes the :8001 desktop server is up and stage_market.py has staged +
// calibrated the session. Light theme, 1920x1080 dsf 2, same conventions as
// capture_market.mjs.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const BASE = (process.argv[2] ?? "http://127.0.0.1:8001").replace(/\/$/, "");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(HERE, "assets", "shots");

const log = (m) => console.log(`[capture_lv3d] ${m}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(page, fn, desc, timeout = 120000, ...args) {
  try {
    await page.waitForFunction(fn, { timeout, polling: 400 }, ...args);
  } catch {
    throw new Error(`timed out waiting for: ${desc}`);
  }
}

/** Grouped TopBar nav (2026-07 shell): open the group dropdown, pick the leaf. */
async function openWorkspace(page, group, leaf) {
  const okGroup = await page.evaluate((group) => {
    const btns = [...document.querySelectorAll('nav[aria-label="Workspaces"] button')];
    const b = btns.find((b) => b.textContent.trim().startsWith(group));
    if (!b) return false;
    b.click();
    return true;
  }, group);
  if (!okGroup) throw new Error(`nav group "${group}" not found`);
  await sleep(400);
  const okLeaf = await page.evaluate((leaf) => {
    const btns = [...document.querySelectorAll("button")].filter((b) => b.offsetParent !== null);
    const b = btns.find((b) => b.textContent.trim() === leaf && !b.disabled);
    if (!b) return false;
    b.click();
    return true;
  }, leaf);
  if (!okLeaf) throw new Error(`workspace "${leaf}" not found or disabled in "${group}"`);
  log(`workspace -> ${group} · ${leaf}`);
  await sleep(600);
}

async function clickButton(page, text) {
  const ok = await page.evaluate((text) => {
    const btns = [...document.querySelectorAll("button")].filter((b) => b.offsetParent !== null);
    const b = btns.find((b) => b.textContent.trim() === text);
    if (!b) return false;
    b.click();
    return true;
  }, text);
  if (!ok) throw new Error(`button "${text}" not found`);
  log(`click -> ${text}`);
  await sleep(400);
}

async function setSelect(page, finder, { value }) {
  const result = await page.evaluate(
    (finder, value) => {
      let sel = null;
      if (finder.label) {
        const lab = [...document.querySelectorAll("label")].find(
          (l) => l.textContent.trim().startsWith(finder.label) && l.querySelector("select"),
        );
        sel = lab ? lab.querySelector("select") : null;
      }
      if (!sel || sel.offsetParent === null) return `select not found (${JSON.stringify(finder)})`;
      const opts = [...sel.options].map((o) => o.value);
      if (!opts.includes(value)) return `option "${value}" not in [${opts.join(", ")}]`;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
      setter.call(sel, value);
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      return `ok:${value}`;
    },
    finder,
    value,
  );
  if (!String(result).startsWith("ok:")) throw new Error(`setSelect failed: ${result}`);
  log(`select ${JSON.stringify(finder)} -> ${value}`);
  await sleep(600);
}

async function main() {
  if (!fs.existsSync(EDGE)) throw new Error(`Edge not found at ${EDGE}`);
  fs.mkdirSync(SHOTS, { recursive: true });
  log(`backend: ${BASE}`);

  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: true,
    args: ["--force-color-profile=srgb", "--hide-scrollbars", "--window-size=1920,1080"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 2 });
  await page.evaluateOnNewDocument(() => {
    localStorage.setItem(
      "volfit.viewSettings",
      JSON.stringify({ scheme: "light", contrast: 1, brightness: 1 }),
    );
  });

  try {
    await page.goto(BASE + "/", { waitUntil: "networkidle2", timeout: 120000 });
    await waitFor(page, () => !!document.querySelector('nav[aria-label="Workspaces"]'), "app shell");
    await waitFor(
      page,
      () => [...document.querySelectorAll("span")].some((s) => s.textContent.trim() === "LIVE"),
      "LIVE badge (backend reachable, not mock)",
    );
    await page.evaluate(() => document.fonts.ready);

    await openWorkspace(page, "Surfaces", "Local Vol");
    // First open triggers the affine fit — wait for the smile to render.
    await waitFor(
      page,
      () =>
        ![...document.querySelectorAll("main div")].some((d) =>
          d.textContent.trim().startsWith("Calibrating local-vol surface"),
        ) && [...document.querySelectorAll("main svg path")].length >= 1,
      "local-vol surface calibrated + smile rendered",
      420000,
    );
    await setSelect(page, { label: "Underlying" }, { value: "SPY" });
    await waitFor(
      page,
      () =>
        ![...document.querySelectorAll("main div")].some((d) =>
          d.textContent.trim().startsWith("Calibrating local-vol surface"),
        ) && [...document.querySelectorAll("main svg path")].length >= 1,
      "SPY local-vol surface calibrated",
      420000,
    );

    // LV surface sub-tab: the 3D triangulated local-variance mesh is default.
    await clickButton(page, "LV surface");
    await waitFor(
      page,
      () => {
        const svgs = [...document.querySelectorAll("main svg")];
        return svgs.reduce((c, s) => c + s.querySelectorAll("path").length, 0) >= 6;
      },
      "3D LV mesh rendered (svg paths)",
      120000,
    );
    await sleep(1500); // settle transitions
    await page.screenshot({ path: path.join(SHOTS, "localvol_mesh3d.png") });
    log("SHOT localvol_mesh3d.png (full viewport)");
  } catch (err) {
    await page.screenshot({ path: path.join(SHOTS, "_debug_lv3d.png") }).catch(() => {});
    throw err;
  } finally {
    await browser.close();
  }
  log("done");
}

main().catch((e) => {
  console.error(`[capture_lv3d] FAILED: ${e.message}`);
  process.exit(1);
});

// Headless-Edge UI smoke (npm run smoke:ui): builds nothing, drives the
// PREVIEW server through the WORKBENCH SHELL (UI SHELL v2) and fails on any
// uncaught page error or ErrorBoundary fallback:
//   1. every lens of the activity bar (Graph · Forwards · Parametric · Local
//      Vol · Quality) on the auto-opened node tab, plus the Parametric
//      "Compare" sub-view;
//   2. the nodes pane → tab round trip (click a node row, a tab appears);
//   3. every top-bar menu (Universe · Help · View · Layout) and every dialog
//      (Options · Manage universe · Keyboard shortcuts · About · Quick open).
// Backend-optional by design: without :8000 the session falls back to the
// mock smile and the live-only lenses show their offline cards — the smoke
// asserts the shell never white-screens, not that data loaded. Screenshots
// land in .smoke/.
//
// Prereqs: `npm run build` (vite preview serves dist/), Microsoft Edge.
import { mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4188; // off the dev/preview defaults so a running app never collides
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");

const LENSES = [
  { name: "Graph" },
  { name: "Forwards" },
  { name: "Parametric" },
  // Sub-view of the Parametric chart card (V3.2 model comparison): clicked
  // via its SegmentedControl button after the lens mounts.
  { name: "Parametric", subview: "Compare", slug: "compare" },
  { name: "Local Vol" },
  { name: "Quality" },
];
const MENUS = ["Universe", "Help", "View", "Layout"];
// Dialogs: opened from the top bar (Options) / activity bar (Manage universe) /
// Help menu (shortcuts) / brand (About). Each must render role="dialog".
const DIALOGS = [
  { name: "Options", open: (p) => clickHeader(p, "Options") },
  { name: "Manage universe", open: (p) => clickAria(p, "Manage universe") },
  { name: "Keyboard shortcuts", open: async (p) => { await clickHeader(p, "Help"); await clickText(p, "Keyboard shortcuts"); } },
  { name: "About VolFit", open: (p) => clickHeader(p, "About VolFit", "title") },
  // Ctrl+P quick-open palette (role=dialog "Quick open").
  { name: "Quick open", open: async (p) => { await p.keyboard.down("Control"); await p.keyboard.press("KeyP"); await p.keyboard.up("Control"); } },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickHeader(page, label, attr = "text") {
  const sel = attr === "title"
    ? `xpath/.//header//button[@title="${label}"]`
    : `xpath/.//header//button[.//span[normalize-space()="${label}"] or normalize-space()="${label}"]`;
  const [btn] = await page.$$(sel);
  if (!btn) throw new Error(`header button "${label}" not found`);
  await btn.click();
  await sleep(200);
}
async function clickAria(page, label) {
  const btn = await page.$(`button[aria-label="${label}"]`);
  if (!btn) throw new Error(`button[aria-label="${label}"] not found`);
  await btn.click();
  await sleep(200);
}
async function clickText(page, label) {
  const [btn] = await page.$$(`xpath/.//span[normalize-space()="${label}"]/ancestor::button[1]`);
  if (!btn) throw new Error(`row "${label}" not found`);
  await btn.click();
  await sleep(200);
}

function startPreview() {
  // Spawn the vite JS bin through THIS node: no .cmd shim (Node >= 20 EINVALs
  // on .cmd spawns without a shell) and no PATH dependence.
  const viteBin = new URL("../node_modules/vite/bin/vite.js", import.meta.url)
    .pathname.replace(/^\/(\w:)/, "$1");
  const proc = spawn(
    process.execPath,
    [viteBin, "preview", "--port", String(PORT), "--strictPort"],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("vite preview did not start")), 20000);
    proc.stdout.on("data", (buf) => {
      const plain = String(buf).replace(/\x1b\[[0-9;]*m/g, "");
      if (plain.includes("Local:")) {
        clearTimeout(timer);
        resolve(proc);
      }
    });
    proc.on("exit", (code) => reject(new Error(`vite preview exited (${code})`)));
  });
}

const preview = await startPreview();
mkdirSync(OUT, { recursive: true });
let failures = 0;
const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: true,
  args: ["--no-first-run", "--disable-gpu"],
});

/** Assert the shell is healthy after a step; screenshot either way. */
async function check(page, pageErrors, name) {
  const crashed = await page.evaluate(() => document.body.innerText.includes("hit an error"));
  const empty = await page.evaluate(() => document.querySelector("main")?.innerText.trim() === "");
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  await page.screenshot({ path: `${OUT}${slug}.png` });
  if (crashed || empty || pageErrors.length > 0) {
    console.error(`FAIL ${name}: crashed=${crashed} empty=${empty} pageErrors=${pageErrors.length}`);
    pageErrors.forEach((e) => console.error(`  ${e}`));
    pageErrors.length = 0;
    failures += 1;
    return false;
  }
  console.log(`ok   ${name}`);
  return true;
}

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 30000 });
  await sleep(800);

  // 1. Lenses (the session auto-opens a preview tab for its default node).
  for (const lens of LENSES) {
    try {
      await clickAria(page, lens.name);
      await sleep(700);
      if (lens.subview) {
        const [sub] = await page.$$(`xpath/.//main//button[normalize-space()="${lens.subview}"]`);
        if (!sub) throw new Error(`subview "${lens.subview}" not found`);
        await sub.click();
        await sleep(700);
      }
      await check(page, pageErrors, lens.slug ?? lens.name);
    } catch (err) {
      console.error(`FAIL ${lens.slug ?? lens.name}: ${err.message}`);
      failures += 1;
    }
  }

  // 2. Nodes pane → tab: click the first expiry row; the strip must show a tab.
  try {
    await clickAria(page, "Parametric");
    const rows = await page.$$('[role="tree"] [role="treeitem"][aria-selected]');
    if (rows.length === 0) throw new Error("no node rows in the Nodes pane");
    await rows[0].click();
    await sleep(500);
    const tabs = await page.$$('[role="tablist"] [role="tab"]');
    if (tabs.length === 0) throw new Error("no tab after clicking a node");
    await check(page, pageErrors, "nodes-pane-tab");
  } catch (err) {
    console.error(`FAIL nodes-pane-tab: ${err.message}`);
    failures += 1;
  }

  // 3. Menus open + close (Esc / backdrop).
  for (const m of MENUS) {
    try {
      await clickHeader(page, m);
      await check(page, pageErrors, `menu-${m}`);
      await page.keyboard.press("Escape");
      await page.mouse.click(700, 450); // click-away backdrop
      await sleep(150);
    } catch (err) {
      console.error(`FAIL menu-${m}: ${err.message}`);
      failures += 1;
    }
  }

  // 4. Dialogs render + Esc closes them.
  for (const d of DIALOGS) {
    try {
      await d.open(page);
      await sleep(400);
      const dialog = await page.$('[role="dialog"]');
      if (!dialog) throw new Error("no role=dialog rendered");
      await check(page, pageErrors, `dialog-${d.name}`);
      await page.keyboard.press("Escape");
      await sleep(200);
      if (await page.$('[role="dialog"]')) throw new Error("dialog did not close on Esc");
    } catch (err) {
      console.error(`FAIL dialog-${d.name}: ${err.message}`);
      failures += 1;
      await page.keyboard.press("Escape");
    }
  }
} finally {
  await browser.close();
  preview.kill();
}

if (failures > 0) {
  console.error(`\nUI smoke: ${failures} step(s) failed (screenshots in .smoke/)`);
  process.exit(1);
}
console.log(`\nUI smoke: shell, ${LENSES.length} lens steps, ${MENUS.length} menus, ${DIALOGS.length} dialogs render (screenshots in .smoke/)`);

// Headless-Edge UI smoke (npm run smoke:ui): builds nothing, drives the
// PREVIEW server through every workspace tab and fails on any uncaught page
// error or ErrorBoundary fallback. Backend-optional by design: without
// :8000 the Parametric tab falls back to the mock smile and the live-only
// views show their offline cards — the smoke asserts the shell never
// white-screens, not that data loaded. Screenshots land in .smoke/.
//
// Prereqs: `npm run build` (vite preview serves dist/), Microsoft Edge.
import { mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 4188; // off the dev/preview defaults so a running app never collides
// Workspaces behind the grouped top-bar menus: open `menu`, click `item`
// (menu: null = a direct tab; "VolFit" = the brand menu holding Options/View).
const TABS = [
  { name: "Parametric", menu: "Surfaces", item: "Parametric" },
  { name: "Local Vol", menu: "Surfaces", item: "Local Vol" },
  { name: "Forwards", menu: "Surfaces", item: "Forwards" },
  { name: "Options", menu: "VolFit", item: "Options" },
  { name: "Graph", menu: "Universe", item: "Graph" },
  { name: "Quality", menu: null, item: "Quality" },
  { name: "Universe", menu: "Universe", item: "Selection" },
  { name: "View", menu: "VolFit", item: "View" },
];
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");

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
      // Vite colors its banner; strip ANSI codes before matching "Local:".
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
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 30000 });

  for (const tab of TABS) {
    let button;
    if (tab.menu === null) {
      // Direct tab (Quality): its header button carries the label.
      [button] = await page.$$(`xpath/.//header//button[contains(normalize-space(), "${tab.name}")]`);
    } else {
      // Open the group / brand menu, then click the item row (its label lives
      // in a dedicated <span> inside the MenuItem button).
      const [trigger] = await page.$$(
        `xpath/.//header//button[contains(normalize-space(), "${tab.menu}")]`,
      );
      if (trigger) {
        await trigger.click();
        await new Promise((r) => setTimeout(r, 150));
        [button] = await page.$$(
          `xpath/.//span[normalize-space()="${tab.item}"]/ancestor::button[1]`,
        );
      }
    }
    if (!button) {
      console.error(`FAIL ${tab.name}: menu path ${tab.menu ?? "(direct)"} → ${tab.item} not found`);
      failures += 1;
      continue;
    }
    await button.click();
    await new Promise((r) => setTimeout(r, 700)); // let the view mount/fetch-fail
    const crashed = await page.evaluate(() =>
      document.body.innerText.includes("hit an error"),
    );
    const empty = await page.evaluate(() => document.querySelector("main")?.innerText.trim() === "");
    const slug = tab.name.toLowerCase().replace(/\s+/g, "-");
    await page.screenshot({ path: `${OUT}${slug}.png` });
    if (crashed || empty || pageErrors.length > 0) {
      console.error(`FAIL ${tab.name}: crashed=${crashed} empty=${empty} pageErrors=${pageErrors.length}`);
      pageErrors.forEach((e) => console.error(`  ${e}`));
      pageErrors.length = 0;
      failures += 1;
    } else {
      console.log(`ok   ${tab.name}`);
    }
  }
} finally {
  await browser.close();
  preview.kill();
}

if (failures > 0) {
  console.error(`\nUI smoke: ${failures} tab(s) failed (screenshots in .smoke/)`);
  process.exit(1);
}
console.log(`\nUI smoke: all ${TABS.length} tabs render (screenshots in .smoke/)`);

// Screenshot capture for the Note 14 lecture edition ("Three Priors").
// Usage: node scripts/note14_shots.mjs [port]   (default 8011, single-origin
// backend serving the built bundle). Shots land in .smoke/note14-*.png at
// deviceScaleFactor 2 for print embedding.
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = process.argv[2] ?? "8011";
const OUT = new URL("../.smoke/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: true,
  args: ["--no-first-run", "--disable-gpu", "--force-color-profile=srgb"],
});
let failed = false;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 2 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto(`http://localhost:${PORT}/`, { waitUntil: "networkidle2", timeout: 45000 });

  // Navigate: Universe menu -> Graph.
  const [universeMenu] = await page.$$('xpath/.//header//button[contains(normalize-space(), "Universe")]');
  if (!universeMenu) throw new Error("Universe menu not found");
  await universeMenu.click();
  await sleep(200);
  const [graphTab] = await page.$$('xpath/.//span[normalize-space()="Graph"]/ancestor::button[1]');
  if (!graphTab) throw new Error("Graph menu item not found");
  await graphTab.click();

  // Baseline fit: circles in the network chart.
  try {
    await page.waitForFunction(
      () => document.querySelectorAll("main svg circle").length > 3,
      { timeout: 120000 },
    );
  } catch (err) {
    await page.screenshot({ path: `${OUT}note14-stuck.png` });
    const text = await page.evaluate(() => document.querySelector("main")?.innerText ?? "(no main)");
    console.error(`STUCK — main text:\n${text.slice(0, 900)}`);
    throw err;
  }
  await sleep(900);
  await page.screenshot({ path: `${OUT}note14-baseline.png` });

  const clickButton = async (label) => {
    const [btn] = await page.$$(`xpath/.//button[normalize-space()=${JSON.stringify(label)}]`);
    if (!btn) throw new Error(`button not found: ${label}`);
    await btn.click();
    await sleep(400);
    return btn;
  };
  const dump = async (tag) => {
    const state = await page.evaluate(() => {
      const grab = (root) =>
        [...root.querySelectorAll("button")]
          .map((b) => (b.textContent ?? "").trim().slice(0, 50))
          .filter(Boolean);
      const main = document.querySelector("main") ?? document.body;
      return { buttons: grab(main), text: (main.innerText ?? "").slice(0, 1200) };
    });
    console.log(`--- ${tag} BUTTONS:`, JSON.stringify(state.buttons.slice(0, 60)));
    console.log(`--- ${tag} TEXT:`, JSON.stringify(state.text));
  };

  // Fit all three ticker clusters into view (zoom out twice).
  const [zoomOut] = await page.$$('xpath/.//main//button[normalize-space()="−"]');
  if (zoomOut) { await zoomOut.click(); await sleep(250); await zoomOut.click(); await sleep(400); }

  // Step 1: Layered mode — the relations pane gains the semantics column.
  await clickButton("Layered");
  await sleep(800);
  await dump("LAYERED");
  await page.screenshot({ path: `${OUT}note14-layered-pane.png` });

  // Step 1b: what-if pulse — a clean +1 vol-pt innovation to propagate.
  await clickButton("Manual what-if");
  await sleep(700);
  await dump("WHATIF");
  // Clear any seeded pulses, then apply the canonical calendar-pulse scenario.
  for (const x of await page.$$('xpath/.//main//button[normalize-space()="×"]')) {
    try { await x.click(); await sleep(120); } catch { /* row already gone */ }
  }
  await clickButton("Calendar pulse");
  await sleep(500);
  await dump("PULSE");
  await page.screenshot({ path: `${OUT}note14-whatif-pane.png` });

  // Step 2: Run the layered solve.
  const [runBtn] = await page.$$('xpath/.//button[normalize-space()="Run"]');
  if (!runBtn) throw new Error("Run button not found");
  if (await runBtn.evaluate((b) => b.disabled)) throw new Error("Run disabled");
  await runBtn.click();
  await page.waitForFunction(
    () => [...document.querySelectorAll("button")].some(
      (b) => b.textContent?.trim() === "Run" && !b.disabled),
    { timeout: 120000 },
  );
  await sleep(3500); // wave + particles settled
  await page.mouse.move(30, 600); // park the cursor: no hover tooltips
  await sleep(400);
  await page.screenshot({ path: `${OUT}note14-layered-solved.png` });

  // Element shot: the Relationships pane (layered policy card + dynamics).
  const paneHandle = await page.evaluateHandle(() => {
    const h2 = [...document.querySelectorAll("main h2, main h3")]
      .find((el) => el.textContent?.trim() === "Relationships");
    return h2 ? h2.closest("section, aside, div[class]") : null;
  });
  if (paneHandle.asElement()) {
    await paneHandle.asElement().screenshot({ path: `${OUT}note14-pane-relationships.png` });
  }

  // Step 3: inspect a dark receiver via its Diagnostics row (canvas clicks
  // toggle pulses in what-if mode — rows are the inspection path).
  const rowBox = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("main tr, main [role=\"row\"], main li, main div")]
      .filter((el) => {
        const t = (el.textContent ?? "").replace(/\s+/g, " ");
        return /AAPL 2027-01-22/.test(t) && t.length < 120; // the row, not a container
      });
    if (!rows.length) return null;
    const r = rows[rows.length - 1].getBoundingClientRect();
    return { x: r.x + Math.min(180, r.width / 3), y: r.y + r.height / 2, h: r.height };
  });
  console.log("rowBox:", JSON.stringify(rowBox));
  if (rowBox) await page.mouse.click(rowBox.x, rowBox.y);
  await sleep(1400);
  await dump("INSPECTOR");
  await page.screenshot({ path: `${OUT}note14-inspector.png` });
  const inspHandle = await page.evaluateHandle(() => {
    const h2 = [...document.querySelectorAll("main h2, main h3")]
      .find((el) => el.textContent?.trim() === "Inspector");
    return h2 ? h2.closest("section, aside, div[class]") : null;
  });
  if (inspHandle.asElement()) {
    await inspHandle.asElement().screenshot({ path: `${OUT}note14-pane-inspector.png` });
  }

  // Step 4: the per-relation editor — seed from auto so the semantics column
  // shows populated rows, then shoot the modal.
  const [edgesBtn] = await page.$$('xpath/.//main//button[normalize-space()="Edges"]');
  if (edgesBtn) {
    await edgesBtn.click();
    await sleep(900);
    const [seedBtn] = await page.$$('xpath/.//button[normalize-space()="Seed from auto relations"]');
    if (seedBtn) { await seedBtn.click(); await sleep(900); }
    await dump("EDITOR");
    await page.screenshot({ path: `${OUT}note14-editor.png` });
    const modalHandle = await page.evaluateHandle(() => {
      const h = [...document.querySelectorAll("h2, h3")]
        .find((el) => (el.textContent ?? "").trim().startsWith("Message relations"));
      return h ? h.closest("section, div[class]") : null;
    });
    if (modalHandle.asElement()) {
      await modalHandle.asElement().screenshot({ path: `${OUT}note14-pane-editor.png` });
    }
    await page.keyboard.press("Escape");
  }

  if (pageErrors.length > 0) {
    failed = true;
    pageErrors.forEach((e) => console.error(`pageerror: ${e}`));
  }
} finally {
  await browser.close();
}
console.log(failed ? "note14 shots: FAILED" : "note14 shots: ok");
process.exit(failed ? 1 : 0);

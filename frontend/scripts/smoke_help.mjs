// Help Center smoke step (HELP CENTER ARC), split out of ui_smoke.mjs for the
// file-size policy: Help ▾ lists the full menu; every page of the Help Center
// renders with entries; Ask answers a local query with cards; the nav search
// returns results; F1 opens the guide of the active lens; Ctrl+/ opens the
// Shortcuts page; the Walkthrough overlay starts, finds every anchor, advances
// with ArrowRight and ends on Esc. Returns the number of failed steps (0/1).
export async function smokeHelpCenter(page, pageErrors, { clickHeader, clickText, check, sleep }) {
  // 8. Help Center (HELP CENTER ARC): Help ▾ lists the full menu; every page
  //    of the center renders; F1 opens the guide of the active lens; Ctrl+/
  //    opens the Shortcuts page; Ask answers a local query with cards; the
  //    Walkthrough overlay starts, advances with ArrowRight and ends on Esc.
  try {
    await clickHeader(page, "Help");
    const rows = await page.evaluate(() => Array.from(document.querySelectorAll('header [role="menu"] button, header .absolute button span.flex-1')).length);
    if (rows < 14) throw new Error(`Help menu lists ${rows} rows`);
    await clickText(page, "Welcome");
    await sleep(400);
    const pages = ["welcome", "guides", "commands", "settings", "shortcuts", "glossary", "tips", "docs", "ask", "whatsnew"];
    for (const id of pages) {
      const btn = await page.$(`[data-help-nav="${id}"]`);
      if (!btn) throw new Error(`nav button for ${id} not found`);
      await btn.click();
      await sleep(id === "docs" || id === "settings" ? 700 : 350);
      const shown = await page.$(`[data-help-page="${id}"]`);
      if (!shown) throw new Error(`page ${id} did not render`);
      const cards = await page.evaluate(() => document.querySelectorAll('[data-help-page] article').length);
      console.log(`     help page ${id}: ${cards} entries`);
      if ((id === "commands" || id === "settings" || id === "glossary" || id === "tips") && cards < 10) throw new Error(`page ${id} shows only ${cards} entries`);
      await check(page, pageErrors, `help-${id}`);
    }
    // Ask (local tier): back to the Ask page, type a question, expect result cards.
    await page.click('[data-help-nav="ask"]');
    await sleep(300);
    await page.type('input[aria-label="Ask a question"]', "how do I calibrate only the local vol surface");
    await page.keyboard.press("Enter");
    await sleep(500);
    const hits = await page.evaluate(() => document.querySelectorAll("[data-ask-hit]").length);
    if (hits < 1) throw new Error("Ask returned no local cards");
    console.log(`     ask: ${hits} cards`);
    await check(page, pageErrors, "help-ask-answer");
    // Search box: results replace the page.
    await page.type('input[aria-label="Search help"]', "haircut");
    await sleep(400);
    const results = await page.evaluate(() => document.querySelectorAll('[aria-label="Search results"] [role="listitem"]').length);
    if (results < 1) throw new Error("help search returned nothing for haircut");
    await check(page, pageErrors, "help-search");
    await page.keyboard.press("Escape");
    await sleep(300);
    // F1 → the guide of the active lens (Parametric was last).
    await page.keyboard.press("F1");
    await sleep(500);
    const guide = await page.$('[data-help-page="guides"] h2');
    if (!guide) throw new Error("F1 did not open a guide");
    console.log(`     F1: ${await page.evaluate((el) => el.textContent, guide)}`);
    await check(page, pageErrors, "help-f1-guide");
    await page.keyboard.press("Escape");
    await sleep(300);
    // Ctrl+/ → Shortcuts page.
    await page.keyboard.down("Control"); await page.keyboard.press("Slash"); await page.keyboard.up("Control");
    await sleep(400);
    if (!(await page.$('[data-help-page="shortcuts"]'))) throw new Error("Ctrl+/ did not open the Shortcuts page");
    await page.keyboard.press("Escape");
    await sleep(300);
    // Walkthrough: menu row → overlay; ArrowRight ×3 → step 4; Esc ends it.
    await clickHeader(page, "Help");
    await clickText(page, "Walkthrough…");
    await sleep(600);
    if (!(await page.$("[data-tour-overlay]"))) throw new Error("walkthrough overlay did not appear");
    // Every anchor of the tour must be present in the DOM.
    const missing = await page.evaluate(() => ["brand", "menu.file", "menu.options", "menu.universe", "menu.help", "center", "menu.view", "menu.layout", "activity", "nodes", "tabs", "main", "status"]
      .filter((a) => !document.querySelector(`[data-tour="${a}"]`)));
    if (missing.length) throw new Error(`tour anchors missing: ${missing.join(", ")}`);
    await check(page, pageErrors, "walkthrough-step-1");
    for (let i = 0; i < 3; i++) { await page.keyboard.press("ArrowRight"); await sleep(250); }
    const stepLabel = await page.evaluate(() => document.querySelector("[data-tour-overlay]")?.getAttribute("aria-label") ?? "");
    if (!/step 4 of 12/i.test(stepLabel)) throw new Error(`expected step 4 after three ArrowRight, got "${stepLabel}"`);
    await check(page, pageErrors, "walkthrough-step-4");
    await page.keyboard.press("Escape");
    await sleep(300);
    if (await page.$("[data-tour-overlay]")) throw new Error("walkthrough did not end on Esc");
  } catch (err) {
    console.error(`FAIL help-center: ${err.message}`);
      await page.keyboard.press("Escape");
  }
}

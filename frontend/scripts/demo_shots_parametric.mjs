// Deck screenshots of the PARAMETRIC lens and the shell (2026-09-24) against a
// staged, fully calibrated instance served single-origin on :8011 (never the
// user's :8000 / :5173). Headless Edge, LIGHT theme, 1600×1000 @2x, strictly
// READ-ONLY: menus and dialogs are opened and closed, model chips in Compare
// are lit (GET-only lazy fits), nothing is calibrated, saved, applied or
// deleted. Each shot is independent (try/catch); pass shot names as argv to
// re-run a subset:  node scripts/demo_shots_parametric.mjs smile_table varswap_card
// PNGs land in Docs/deck/assets/shots_demo/; the numbers read off the DOM for
// the README go to shots_demo/_notes.json.
import { mkdirSync, writeFileSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = "http://127.0.0.1:8011";
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../../Docs/deck/assets/shots_demo/", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PAD = 12;

mkdirSync(OUT, { recursive: true });
const notes = {};
const failures = [];

// ---------------------------------------------------------------- helpers
async function waitFor(page, fn, what, ms = 30000, arg = undefined) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn, arg)) return true;
    await sleep(200);
  }
  throw new Error(`timed out waiting for ${what}`);
}
async function full(page, name) {
  await page.screenshot({ path: `${OUT}${name}.png` });
  console.log(`  shot ${name}.png`);
}
/** element.screenshot with ~PAD px around it (clipped to the viewport). */
async function crop(page, handle, name) {
  const box = await handle.boundingBox();
  if (!box) throw new Error(`no box for ${name}`);
  const vp = page.viewport();
  const x = Math.max(0, box.x - PAD), y = Math.max(0, box.y - PAD);
  const clip = { x, y, width: Math.min(vp.width - x, box.width + 2 * PAD), height: Math.min(vp.height - y, box.height + 2 * PAD) };
  await page.screenshot({ path: `${OUT}${name}.png`, clip });
  console.log(`  crop ${name}.png (${Math.round(clip.width)}×${Math.round(clip.height)})`);
}
async function clickHeader(page, label, attr = "text") {
  const sel = attr === "title"
    ? `xpath/.//header//button[starts-with(@title, "${label}")]`
    : `xpath/.//header//button[.//span[normalize-space()="${label}"] or normalize-space()="${label}"]`;
  const [btn] = await page.$$(sel);
  if (!btn) throw new Error(`header button "${label}" not found`);
  await btn.click();
  await sleep(300);
}
async function clickAria(page, label, scope = "") {
  const btn = await page.$(`${scope} button[aria-label="${label}"]`.trim());
  if (!btn) throw new Error(`button[aria-label="${label}"] not found`);
  await btn.click();
  await sleep(300);
}
/** The main-area button with EXACT text (last match when `last`). */
async function clickMain(page, label, { last = false, startsWith = false } = {}) {
  const pred = startsWith ? `starts-with(normalize-space(), "${label}")` : `normalize-space()="${label}"`;
  const xp = last ? `xpath/(.//main//button[${pred}])[last()]` : `xpath/.//main//button[${pred}]`;
  const [btn] = await page.$$(xp);
  if (!btn) throw new Error(`main button "${label}" not found`);
  await btn.click();
  await sleep(400);
}
const text = (page, sel) => page.evaluate((s) => document.querySelector(s)?.innerText?.trim() ?? null, sel);
const chartReady = () =>
  !!document.querySelector("main svg") &&
  document.querySelectorAll('main [data-testid="quote-layer-market"] [data-quote-index]').length >= 5;

/** Deep-link a node into a lens; wait for the chart + settle. */
async function openNode(page, ticker, expiry, activity = "parametric", { wait = "chart" } = {}) {
  await page.goto(`${BASE}/?node=${ticker}|${expiry}&activity=${activity}`, { waitUntil: "networkidle2", timeout: 60000 });
  await page.keyboard.press("Escape");
  if (wait === "chart") {
    // The workbench remembers the last view per tab (Table / Compare…): put
    // the Smile view up explicitly before waiting for its quote markers.
    await waitFor(page, () => Array.from(document.querySelectorAll("main button")).some((b) => b.textContent.trim() === "Smile"), "the Parametric toolbar");
    await clickMain(page, "Smile");
    await waitFor(page, chartReady, `the ${ticker} ${expiry} smile`);
  } else if (wait === "svg") await waitFor(page, () => !!document.querySelector("main svg"), "a main svg");
  await sleep(900);
}
async function ensureNodesPane(page, shown = true) {
  const has = async () => (await page.$('[role="tree"]')) !== null;
  if ((await has()) !== shown) {
    await page.keyboard.down("Control"); await page.keyboard.press("KeyB"); await page.keyboard.up("Control");
    await sleep(500);
  }
  if ((await has()) !== shown) throw new Error(`nodes pane not ${shown ? "shown" : "hidden"}`);
}
async function closeDialogs(page) {
  for (let i = 0; i < 3 && (await page.$('[role="dialog"]')); i++) { await page.keyboard.press("Escape"); await sleep(250); }
}
/** The chart card = the nearest bordered/rounded ancestor of the crosshair svg. */
async function chartCard(page) {
  const h = await page.evaluateHandle(() => {
    let el = document.querySelector("main svg.cursor-crosshair");
    if (!el) return null;
    let up = el;
    for (let i = 0; i < 12 && up; i++) {
      up = up.parentElement;
      if (up && /rounded-(xl|lg)/.test(up.className) && /border/.test(up.className)) return up;
    }
    return el.parentElement?.parentElement ?? el;
  });
  if (!h || !(await h.asElement())) throw new Error("no chart card");
  return h.asElement();
}
/** Open Options and scroll one section card into view (rail click + instant scroll). */
async function optionsSection(page, label, id) {
  if (!(await page.$('[role="dialog"]'))) { await clickHeader(page, "Options"); await sleep(600); }
  await waitFor(page, () => !!document.querySelector('nav[aria-label="Options sections"]'), "the Options rail", 15000);
  const [btn] = await page.$$(`xpath/.//nav[@aria-label="Options sections"]//button[normalize-space()="${label}"]`);
  if (!btn) throw new Error(`Options rail "${label}" not found`);
  await btn.click();
  // The rail scrolls smoothly and the lazy diagnostics tables (Prior / Filter)
  // grow the content after it lands: let both settle, then pin the section's
  // top to the scroll container's top and verify (a few rounds).
  await sleep(1200);
  for (let i = 0; i < 5; i++) {
    const off = await page.evaluate((sid) => {
      const el = document.getElementById(sid);
      if (!el) return null;
      const sc = el.closest(".overflow-y-auto");
      if (!sc) { el.scrollIntoView({ block: "start", behavior: "instant" }); return 0; }
      sc.scrollTop += el.getBoundingClientRect().top - sc.getBoundingClientRect().top - 4;
      return el.getBoundingClientRect().top - sc.getBoundingClientRect().top - 4;
    }, id);
    if (off === null) throw new Error(`#${id} not found`);
    await sleep(450);
    const rest = await page.evaluate((sid) => {
      const el = document.getElementById(sid);
      const sc = el?.closest(".overflow-y-auto");
      return el && sc ? el.getBoundingClientRect().top - sc.getBoundingClientRect().top - 4 : 0;
    }, id);
    // At the bottom of the list the section cannot reach the top: accept a
    // positive rest once the container is scrolled to its end.
    const atEnd = await page.evaluate((sid) => { const sc = document.getElementById(sid)?.closest(".overflow-y-auto"); return sc ? sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2 : true; }, id);
    if (Math.abs(rest) < 3 || (rest > 0 && atEnd)) break;
  }
  await sleep(300);
}
const dump = (page, sel) => page.evaluate((s) => document.querySelector(s)?.innerText ?? null, sel);

// ------------------------------------------------------------------ shots
const SHOTS = {
  async shell_hero(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Smile");
    await ensureNodesPane(page, true);
    await sleep(400);
    notes.shell_hero = { diag: await dump(page, 'section[data-aside-panel="diag"]'), footer: await dump(page, "footer") };
    await full(page, "shell_hero");
  },

  async dialog_universe(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickAria(page, "Manage universe");
    await waitFor(page, () => !!document.querySelector('[role="dialog"]'), "the universe dialog");
    await sleep(900);
    notes.dialog_universe = (await dump(page, '[role="dialog"]'))?.slice(0, 600);
    await full(page, "dialog_universe");
    await closeDialogs(page);
  },

  async dialog_datasources(page) {
    await openNode(page, "QQQ", "2026-12-18");
    const pill = await page.$('header button[title*="Data source & as-of"]');
    if (!pill) throw new Error("market pill not found");
    await pill.click();
    await waitFor(page, () => !!document.querySelector('[role="dialog"]'), "the universe dialog");
    await sleep(800);
    await page.evaluate(() => {
      const h = Array.from(document.querySelectorAll('[role="dialog"] h2')).find((e) => e.textContent.trim() === "Data sources");
      h?.scrollIntoView({ block: "start", behavior: "instant" });
    });
    await sleep(500);
    notes.dialog_datasources = await page.evaluate(() => {
      const h = Array.from(document.querySelectorAll('[role="dialog"] h2')).find((e) => e.textContent.trim() === "Data sources");
      return h?.parentElement?.innerText?.slice(0, 900) ?? null;
    });
    await full(page, "dialog_datasources");
    await closeDialogs(page);
  },

  async fetch_menu(page) {
    await openNode(page, "QQQ", "2026-12-18");
    const [btn] = await page.$$('xpath/.//header//button[normalize-space()="Fetch"]');
    if (!btn) throw new Error("Fetch ▾ not found");
    await btn.click();
    await sleep(900);
    notes.fetch_menu = await page.evaluate(() => Array.from(document.querySelectorAll("header [role=\"menu\"], header .absolute")).map((e) => e.innerText).join("\n---\n").slice(0, 900));
    await full(page, "fetch_menu");
    await page.keyboard.press("Escape");
    await sleep(200);
  },

  async calibrate_scope_menu(page) {
    await openNode(page, "QQQ", "2026-12-18");
    const btn = await page.$('header button[title^="Calibration scope"]');
    if (!btn) throw new Error("Calibrate scope ▾ not found");
    await btn.click();
    await sleep(700);
    notes.calibrate_scope_menu = await page.evaluate(() => Array.from(document.querySelectorAll("header .absolute")).map((e) => e.innerText).join("\n---\n").slice(0, 600));
    await full(page, "calibrate_scope_menu");
    await page.keyboard.press("Escape");
    await sleep(200);
  },

  async dialog_options(page) {
    await openNode(page, "QQQ", "2026-12-18");
    const sections = [
      ["Parametric", "opt-parametric", "dialog_options_parametric"],
      ["Calibration", "opt-calibration", "dialog_options_calibration"],
      ["Prior", "opt-prior", "dialog_options_prior"],
      ["Kalman filter", "opt-filter", "dialog_options_filter"],
      ["Events", "opt-events", "dialog_options_events"],
      ["Graph", "opt-graph", "dialog_options_graph"],
      ["Dynamics", "opt-dynamics", "dialog_options_dynamics"],
    ];
    for (const [label, id, file] of sections) {
      try {
        await optionsSection(page, label, id);
        if (id === "opt-prior") {
          // Config tab first (the default); wait for the Operators chips.
          const [cfg] = await page.$$(`xpath/.//*[@id="opt-prior"]//button[normalize-space()="Config"]`);
          if (cfg) { await cfg.click(); await sleep(500); }
          await waitFor(page, () => /Operators/.test(document.getElementById("opt-prior")?.innerText ?? ""), "the Operators row", 15000).catch(() => {});
        }
        notes[file] = (await dump(page, `#${id}`))?.slice(0, 1200);
        await full(page, file);
        if (id === "opt-prior") {
          const [ev] = await page.$$(`xpath/.//*[@id="opt-prior"]//button[normalize-space()="Evidence"]`);
          if (!ev) throw new Error("Evidence tab not found");
          await ev.click();
          await sleep(1500);
          notes.dialog_options_prior_evidence = (await dump(page, "#opt-prior"))?.slice(0, 1200);
          await full(page, "dialog_options_prior_evidence");
          const [cfg] = await page.$$(`xpath/.//*[@id="opt-prior"]//button[normalize-space()="Config"]`);
          if (cfg) { await cfg.click(); await sleep(300); }
        }
      } catch (err) {
        failures.push(`${file}: ${err.message}`);
        console.error(`FAIL ${file}: ${err.message}`);
      }
    }
    await closeDialogs(page);
  },

  async smile_qqq_dec(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Smile");
    await sleep(500);
    notes.smile_qqq_dec = { title: await dump(page, "main h2"), diag: await dump(page, 'section[data-aside-panel="diag"]'), badges: await page.evaluate(() => Array.from(document.querySelectorAll("main span.font-semibold.tracking-wider")).map((s) => s.textContent)) };
    await full(page, "smile_qqq_dec");
    await crop(page, await chartCard(page), "smile_qqq_dec_chart");
  },

  async smile_table(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Table");
    await waitFor(page, () => document.querySelectorAll("main tbody tr").length >= 10, "the quote table");
    await sleep(600);
    notes.smile_table = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll("main tbody tr")).slice(0, 4).map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent.trim()).join(" | "));
      const head = Array.from(document.querySelectorAll("main thead th")).map((t) => t.textContent.trim()).join(" | ");
      return { head, rows, n: document.querySelectorAll("main tbody tr").length };
    });
    await full(page, "smile_table");
  },

  async smile_density(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Density");
    await waitFor(page, () => !!document.querySelector("main svg"), "the density chart");
    await sleep(900);
    await full(page, "smile_density");
    await clickMain(page, "Log Q-density");
    await sleep(1200);
    await full(page, "smile_logqd");
    await clickMain(page, "CDF");
    await sleep(1200);
    await full(page, "smile_cdf");
    await clickMain(page, "Density", { last: true });
    await sleep(300);
  },

  async smile_compare(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Compare");
    await waitFor(page, () => document.querySelectorAll("main tbody tr").length >= 1, "the Compare table");
    const n0 = await page.evaluate(() => document.querySelectorAll("main tbody tr").length);
    const chips = await page.evaluate(() => Array.from(document.querySelectorAll("main button[aria-pressed]")).map((b) => `${b.textContent.trim()}[${b.getAttribute("aria-pressed")}]`));
    console.log(`  compare chips: ${chips.join(" · ")}`);
    const lit = async (label) => {
      const [b] = await page.$$(`xpath/.//main//button[@aria-pressed and starts-with(normalize-space(), "${label}")]`);
      if (!b) { console.warn(`  chip ${label} missing`); return; }
      const pressed = await page.evaluate((el) => el.getAttribute("aria-pressed"), b);
      if (pressed !== "true") { await b.click(); await sleep(400); }
    };
    await lit("SVI");
    await lit("MCS");
    const ref = await page.$('main button[aria-label="Show reference families"]');
    if (ref) { await ref.click(); await sleep(400); await lit("eSSVI"); }
    await waitFor(page, (n) => document.querySelectorAll("main tbody tr").length > n, "the model rows to grow", 90000, n0).catch((e) => console.warn(`  ${e.message}`));
    // Wait for the lazy fits to land (no "…" / fitting cells).
    await waitFor(page, () => !/fitting|…/.test(Array.from(document.querySelectorAll("main tbody td")).map((t) => t.textContent).join(" ")), "the lazy fits", 90000).catch(() => {});
    await sleep(800);
    notes.smile_compare = await page.evaluate(() => {
      const head = Array.from(document.querySelectorAll("main thead th")).map((t) => t.textContent.trim()).join(" | ");
      const rows = Array.from(document.querySelectorAll("main tbody tr")).map((r) => Array.from(r.querySelectorAll("td")).map((td) => td.textContent.trim()).join(" | "));
      return { head, rows };
    });
    await full(page, "smile_compare");
  },

  async smile_weights_strip(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Smile");
    const btn = await page.$('[aria-label="Chart layers"] button[aria-label="Weights"]');
    if (!btn) throw new Error("Weights layer button missing");
    const pressed = await page.evaluate((el) => el.getAttribute("aria-pressed"), btn);
    if (pressed !== "true") await btn.click();
    await waitFor(page, () => document.querySelectorAll('[data-testid="weight-strip"] [data-quote-index]').length >= 5, "the weight strip");
    await sleep(600);
    notes.smile_weights_strip = await dump(page, '[data-testid="weight-strip"]');
    await full(page, "smile_weights_strip");
    await btn.click(); // back off
    await sleep(200);
  },

  async smile_fit_switch(page) {
    await openNode(page, "XOM", "2027-01-15");
    await clickMain(page, "Smile");
    // The INFERRED · GRAPH badge (a server-side graph Run) crowds this narrow
    // card's toolbar: switch the Graph layer off (a view toggle, nothing saved).
    const graphLayer = await page.$('[aria-label="Chart layers"] button[aria-label="Graph"]');
    if (graphLayer && (await page.evaluate((el) => el.getAttribute("aria-pressed") === "true", graphLayer))) { await graphLayer.click(); await sleep(500); }
    await waitFor(page, () => !!document.querySelector("main [data-fit-anchoring]"), "the Fit switch", 15000);
    const opts = await page.evaluate(() => Array.from(document.querySelectorAll("main [data-fit-anchoring] button")).map((b) => b.textContent.trim()));
    console.log(`  fit switch: ${opts.join(" / ")}`);
    notes.smile_fit_switch = { options: opts };
    const pick = async (label, file) => {
      let [b] = await page.$$(`xpath/.//main//*[@data-fit-anchoring]//button[normalize-space()="${label}"]`);
      let shadow = true;
      if (!b && label === "+ Prior") {
        // On a node whose saved prior is ACTIVE the prior-anchored fit IS the
        // production fit (Compare tags "+ Prior" PROD), so the switch offers
        // no "+ Prior" shadow: the Production face is that cell.
        [b] = await page.$$(`xpath/.//main//*[@data-fit-anchoring]//button[normalize-space()="Production"]`);
        shadow = false;
        notes.smile_fit_switch.priorNote = "+ Prior is the production cell on this node (no shadow offered); shot shows Production";
      }
      if (!b) throw new Error(`Fit switch "${label}" absent (options: ${opts.join(" / ")})`);
      await b.click();
      if (shadow) await waitFor(page, () => (document.querySelector("main")?.innerText ?? "").includes("SHADOW ·"), `the SHADOW tag for ${label}`, 60000);
      else await waitFor(page, () => !(document.querySelector("main")?.innerText ?? "").includes("SHADOW ·"), "the production face", 60000);
      await sleep(900);
      notes.smile_fit_switch[file] = { diag: await dump(page, 'section[data-aside-panel="diag"]'), tag: await page.evaluate(() => (document.querySelector("main")?.innerText.match(/SHADOW · \S+/) ?? [null])[0]) };
      await full(page, file);
    };
    try { await pick("+ Prior", "smile_fit_switch_prior"); } catch (e) { failures.push(`smile_fit_switch_prior: ${e.message}`); console.error(`FAIL smile_fit_switch_prior: ${e.message}`); }
    try { await pick("Free", "smile_fit_switch_free"); } catch (e) { failures.push(`smile_fit_switch_free: ${e.message}`); console.error(`FAIL smile_fit_switch_free: ${e.message}`); }
    const [prod] = await page.$$(`xpath/.//main//*[@data-fit-anchoring]//button[normalize-space()="Production"]`);
    if (prod) await prod.click();
  },

  async fit_diagnostics_card(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Smile");
    const expand = await page.$('button[aria-label="Expand Fit diagnostics"]');
    if (expand) { await expand.click(); await sleep(500); }
    const again = await page.$('button[aria-label="Expand Fit diagnostics"]'); // M → L
    if (again) { await again.click(); await sleep(500); }
    const card = await page.$('section[data-aside-panel="diag"]');
    if (!card) throw new Error("Fit diagnostics card missing");
    notes.fit_diagnostics_card = await dump(page, 'section[data-aside-panel="diag"]');
    await crop(page, card, "fit_diagnostics_card");
    const shrink = await page.$('button[aria-label="Shrink Fit diagnostics"]');
    if (shrink) await shrink.click();
  },

  async varswap_card(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await clickMain(page, "Smile");
    const expand = await page.$('button[aria-label="Expand Variance swap"]');
    if (expand) { await expand.click(); await sleep(500); }
    const card = await page.$('section[data-aside-panel="varswap"]');
    if (!card) throw new Error("Variance swap card missing (Options-gated?)");
    notes.varswap_card = await dump(page, 'section[data-aside-panel="varswap"]');
    await crop(page, card, "varswap_card");
    const shrink = await page.$('button[aria-label="Shrink Variance swap"]');
    if (shrink) await shrink.click();
  },

  async term_events_aapl(page) {
    await openNode(page, "AAPL", "2026-11-20");
    await clickMain(page, "Term");
    await waitFor(page, () => !!document.querySelector("main svg.cursor-crosshair"), "the Term chart", 60000);
    await sleep(1200);
    await page.evaluate(() => {
      const h = Array.from(document.querySelectorAll("main h3")).find((e) => e.textContent.trim() === "Auto-calibrate events");
      h?.scrollIntoView({ block: "end", behavior: "instant" });
    });
    await sleep(400);
    notes.term_events_aapl = { spread: await text(page, '[data-testid="ladder-spread"]'), panel: (await page.evaluate(() => document.querySelector("main aside")?.innerText ?? null))?.slice(0, 900) };
    await full(page, "term_events_aapl");
    await clickMain(page, "Event-dilated");
    await sleep(1000);
    await full(page, "term_events_aapl_dilated");
    await clickMain(page, "Real time");
    await sleep(300);
  },

  async ticker_views(page) {
    await openNode(page, "QQQ", "2026-12-18");
    const views = [["Stacked IV", "stacked_iv"], ["Densities", "densities"], ["Surface", "surface_3d"]];
    for (const [label, file] of views) {
      try {
        await clickMain(page, label);
        await waitFor(page, () => !!document.querySelector("main svg"), `the ${label} chart`, 60000);
        if (label === "Surface") {
          await waitFor(page, () => !!document.querySelector("main svg.cursor-grab"), "the 3D surface", 60000);
          await sleep(1500);
          const svg = await page.$("main svg.cursor-grab");
          const box = await svg.boundingBox();
          await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.45, { steps: 6 });
        }
        await sleep(1500);
        await full(page, file);
      } catch (err) { failures.push(`${file}: ${err.message}`); console.error(`FAIL ${file}: ${err.message}`); }
    }
    await page.mouse.move(5, 5);
  },

  async quality_dashboard(page) {
    await openNode(page, "QQQ", "2026-12-18", "quality", { wait: "none" });
    await clickAria(page, "Quality");
    await waitFor(page, () => (document.querySelector("main")?.innerText ?? "").length > 200, "the Quality lens", 60000);
    await sleep(2500);
    notes.quality_dashboard = (await dump(page, "main"))?.slice(0, 1500);
    await full(page, "quality_dashboard");
  },

  async filter_panel_timeline(page) {
    await openNode(page, "QQQ", "2026-12-18");
    // The FILTER badge on the smile (if the filter is active on this node).
    const badge = await page.evaluate(() => Array.from(document.querySelectorAll("main span.font-semibold.tracking-wider")).map((s) => s.textContent).includes("FILTER"));
    notes.smile_filter_badge = { badge };
    if (badge) await crop(page, await chartCard(page), "smile_filter_badge");
    else console.log("  no FILTER badge on QQQ Dec (skipping smile_filter_badge)");
    await optionsSection(page, "Kalman filter", "opt-filter");
    const [tl] = await page.$$(`xpath/.//*[@id="opt-filter"]//button[normalize-space()="Timeline"]`);
    if (tl) {
      // The toggle sits at the BOTTOM of the section: scrolled into view by a
      // plain click it lands under the sticky Reset / Save / Apply bar, which
      // swallows the click. Pin it to the top of the container first, click,
      // and verify the timeline section mounted (its Live chip / selectors).
      const pin = () => page.evaluate((el) => {
        const sc = el.closest(".overflow-y-auto");
        if (sc) sc.scrollTop += el.getBoundingClientRect().top - sc.getBoundingClientRect().top - 8;
      }, tl);
      // ON = the toggle's pressed classes (bg-accent…); the section's own
      // selects (mode / route / clock) must not count as the timeline.
      const mounted = () => page.evaluate((el) => /bg-accent/.test(el.className), tl);
      for (let i = 0; i < 2 && !(await mounted()); i++) {
        await pin(); await sleep(300);
        await tl.click(); await sleep(1500);
      }
      await waitFor(page, () => document.querySelectorAll("#opt-filter svg").length >= 1, "the timeline charts", 20000).catch((e) => console.warn(`  ${e.message}`));
      await sleep(1200);
      await pin(); await sleep(600);
      notes.filter_timeline_toggle = (await mounted()) ? "on" : "click did not mount the section";
    } else { notes.filter_timeline_toggle = "absent"; console.warn("  no Timeline toggle in the Kalman section"); }
    notes.filter_panel_timeline = (await dump(page, "#opt-filter"))?.slice(0, 1500);
    await full(page, "filter_panel_timeline");
    if (tl) { await tl.click().catch(() => {}); }
    await closeDialogs(page);
  },

  async market_pill_tooltip(page) {
    await openNode(page, "QQQ", "2026-12-18");
    const pill = await page.$('header button[title*="Data source & as-of"]');
    if (!pill) throw new Error("market pill not found");
    const box = await pill.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 4 });
    await sleep(1200);
    // Native title tooltips are drawn by the OS and never reach a headless
    // capture: render the SAME title text as a tooltip under the pill.
    const title = await page.evaluate((b) => {
      const t = b.getAttribute("title") ?? "";
      const r = b.getBoundingClientRect();
      const tip = document.createElement("div");
      tip.id = "__demo_tip";
      tip.textContent = t;
      Object.assign(tip.style, { position: "fixed", left: `${Math.max(8, r.left - 40)}px`, top: `${r.bottom + 6}px`, maxWidth: "460px", whiteSpace: "pre-line", font: "11px/1.35 system-ui, Segoe UI, sans-serif", color: "#1e293b", background: "#fff", border: "1px solid #cbd5e1", borderRadius: "6px", padding: "6px 8px", boxShadow: "0 4px 14px rgba(15,23,42,.14)", zIndex: 9999 });
      document.body.appendChild(tip);
      return t;
    }, pill);
    notes.market_pill_tooltip = title;
    await sleep(200);
    await page.screenshot({ path: `${OUT}market_pill_tooltip.png`, clip: { x: 0, y: 0, width: 1600, height: 140 } });
    console.log("  crop market_pill_tooltip.png");
    await page.evaluate(() => document.getElementById("__demo_tip")?.remove());
    await page.mouse.move(5, 5);
  },

  async status_bar(page) {
    await openNode(page, "QQQ", "2026-12-18");
    await sleep(500);
    notes.status_bar = await dump(page, "footer");
    const vp = page.viewport();
    await page.screenshot({ path: `${OUT}status_bar.png`, clip: { x: 0, y: vp.height - 60, width: vp.width, height: 60 } });
    console.log("  crop status_bar.png");
  },
};

// ------------------------------------------------------------------- main
const wanted = process.argv.slice(2);
const names = wanted.length ? wanted : Object.keys(SHOTS);
for (const n of names) if (!SHOTS[n]) { console.error(`unknown shot ${n}; known: ${Object.keys(SHOTS).join(", ")}`); process.exit(2); }

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 2 });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  await page.evaluateOnNewDocument(() => {
    localStorage.setItem("volfit.viewSettings", JSON.stringify({ scheme: "light", contrast: 1, brightness: 1 }));
    localStorage.setItem("volfit.help.v1", JSON.stringify({ seenWelcome: true, tourDone: true, tourStep: 0, lastLink: "welcome" }));
  });
  for (const n of names) {
    console.log(`> ${n}`);
    try {
      await closeDialogs(page);
      await SHOTS[n](page);
    } catch (err) {
      failures.push(`${n}: ${err.message}`);
      console.error(`FAIL ${n}: ${err.message}`);
      try { await page.screenshot({ path: `${OUT}_fail_${n}.png` }); } catch { /* ignore */ }
    }
  }
  if (pageErrors.length) console.warn(`page errors: ${pageErrors.slice(0, 5).join(" | ")}`);
} finally {
  await browser.close();
}
writeFileSync(`${OUT}_notes${wanted.length ? "_" + wanted.join("_") : ""}.json`, JSON.stringify(notes, null, 2));
console.log(failures.length ? `\n${failures.length} failure(s):\n  ${failures.join("\n  ")}` : "\nall shots taken");

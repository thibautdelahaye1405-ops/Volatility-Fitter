// Deck screenshot capture — GRAPH + FILTER session (synthetic, staged by
// stage_graph.py against the same :8001 server).
//
// REV 7 (2026-07-27): rewritten for the three-pane graph shell (P5b U0-U7 +
// V1-V3) and the grouped TopBar nav. The solve runs the production default
// operator (precision messages; the Propagation segment is set explicitly).
//
// Run from frontend\ (puppeteer-core is installed there):
//     node .\capture_graph.mjs [http://127.0.0.1:8001]
//
// Shots: graph_extrapolate (full shell, post-Run), graph_lattice_content
// (canvas card clip), edge_editor (the "Message relations" policy editor),
// graph_sandbox (unified what-if, Cross-basket scenario), smile_hero (full
// Parametric view w/ GRAPH overlay), smile_hero_wide (chart-card clip),
// filter_smile, filter_panel (#opt-filter card), options_calibration_crop
// (#opt-prior card — the prior-persistence panel + diagnostics).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const BASE = (process.argv[2] ?? "http://127.0.0.1:8001").replace(/\/$/, "");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(HERE, "assets", "shots");

const log = (m) => console.log(`[capture_graph] ${m}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- helpers
async function waitForCalibrationIdle(timeoutS = 300) {
  const deadline = Date.now() + timeoutS * 1000;
  for (;;) {
    const st = await (await fetch(`${BASE}/calibration/status`)).json();
    if (!st.running) return st;
    log(`  calibration running ${st.done}/${st.total} — waiting`);
    if (Date.now() > deadline) throw new Error("calibration never went idle");
    await sleep(2000);
  }
}

async function waitFor(page, fn, desc, timeout = 120000, ...args) {
  try {
    await page.waitForFunction(fn, { timeout, polling: 400 }, ...args);
  } catch {
    throw new Error(`timed out waiting for: ${desc}`);
  }
}

/** Grouped TopBar nav: open the group dropdown, then pick the leaf. */
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
    const btns = [...document.querySelectorAll('nav[aria-label="Workspaces"] button')].filter(
      (b) => b.offsetParent !== null,
    );
    const b = btns.find((b) => b.textContent.trim() === leaf && !b.disabled);
    if (!b) return false;
    b.click();
    return true;
  }, leaf);
  if (!okLeaf) throw new Error(`workspace "${leaf}" not found in "${group}"`);
  log(`workspace -> ${group} · ${leaf}`);
  await sleep(600);
}

/** Brand menu (σ VolFit ▾) → item by its inner span text ("Options", "View"). */
async function openBrandMenuItem(page, item) {
  const okTrig = await page.evaluate(() => {
    const b = [...document.querySelectorAll("header button, button")].find(
      (b) => b.getAttribute("title") === "Settings & app menu" && b.offsetParent !== null,
    );
    if (!b) return false;
    b.click();
    return true;
  });
  if (!okTrig) throw new Error("brand menu trigger not found");
  await sleep(400);
  const okItem = await page.evaluate((item) => {
    const btns = [...document.querySelectorAll("button")].filter((b) => b.offsetParent !== null);
    const b = btns.find((b) => {
      const span = b.querySelector("span.flex-1");
      return span && span.textContent.trim() === item;
    });
    if (!b) return false;
    b.click();
    return true;
  }, item);
  if (!okItem) throw new Error(`brand menu item "${item}" not found`);
  log(`brand menu -> ${item}`);
  await sleep(600);
}

/** Click the first VISIBLE button matching exact trimmed text (or title). */
async function clickButton(page, text, { contains = false, title = null } = {}) {
  const ok = await page.evaluate(
    (text, contains, title) => {
      const btns = [...document.querySelectorAll("button")].filter(
        (b) => b.offsetParent !== null && b.getAttribute("aria-hidden") !== "true",
      );
      const b = btns.find((b) => {
        if (title !== null) return b.getAttribute("title") === title;
        const t = b.textContent.trim();
        return contains ? t.includes(text) : t === text;
      });
      if (!b || b.disabled) return false;
      b.click();
      return true;
    },
    text,
    contains,
    title,
  );
  if (!ok) throw new Error(`button "${title ?? text}" not found or disabled`);
  log(`click -> ${title ?? text}`);
  await sleep(400);
}

async function setSelect(page, finder, { value = null, index = null } = {}) {
  const result = await page.evaluate(
    (finder, value, index) => {
      let sel = null;
      if (finder.title) sel = document.querySelector(`select[title="${finder.title}"]`);
      else if (finder.label) {
        const lab = [...document.querySelectorAll("label")].find(
          (l) => l.textContent.trim().startsWith(finder.label) && l.querySelector("select"),
        );
        sel = lab ? lab.querySelector("select") : null;
      }
      if (!sel || sel.offsetParent === null) return `select not found (${JSON.stringify(finder)})`;
      const opts = [...sel.options].map((o) => o.value);
      let v = value;
      if (v === null) {
        if (index === null) return "no value/index given";
        v = opts[Math.min(index, opts.length - 1)];
      }
      if (!opts.includes(v)) return `option "${v}" not in [${opts.join(", ")}]`;
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLSelectElement.prototype,
        "value",
      ).set;
      setter.call(sel, v);
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      return `ok:${v}`;
    },
    finder,
    value,
    index,
  );
  if (!String(result).startsWith("ok:")) throw new Error(`setSelect failed: ${result}`);
  log(`select ${JSON.stringify(finder)} -> ${String(result).slice(3)}`);
  await sleep(600);
}

async function shotFull(page, name) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
  log(`SHOT ${name}.png (full viewport)`);
}

async function shotElement(page, name, markFn, ...args) {
  await page.evaluate(() => {
    document.querySelectorAll("[data-shot-target]").forEach((e) =>
      e.removeAttribute("data-shot-target"),
    );
  });
  const ok = await page.evaluate(markFn, ...args);
  if (!ok) throw new Error(`shot "${name}": target element not found`);
  const el = await page.$('[data-shot-target="1"]');
  if (!el) throw new Error(`shot "${name}": marked element vanished`);
  await el.screenshot({ path: path.join(SHOTS, `${name}.png`) });
  await page.evaluate(() => {
    document.querySelectorAll("[data-shot-target]").forEach((e) =>
      e.removeAttribute("data-shot-target"),
    );
  });
  log(`SHOT ${name}.png (element clip)`);
}

/** Wait for extrapolation result rows (lit/dark chips) in the bottom drawer's
 *  Diagnostics tab (it opens automatically after a Run). */
async function waitResultsRows(page, minRows = 8, timeout = 300000) {
  await waitFor(
    page,
    (minRows) => {
      const chips = [...document.querySelectorAll("main span")].filter((s) => {
        const t = s.textContent.trim();
        return t === "dark" || t === "lit";
      });
      return chips.length >= minRows;
    },
    `>= ${minRows} extrapolation result rows`,
    timeout,
    minRows,
  );
}

// ------------------------------------------------------------------ main
async function main() {
  if (!fs.existsSync(EDGE)) throw new Error(`Edge not found at ${EDGE}`);
  fs.mkdirSync(SHOTS, { recursive: true });
  log(`backend: ${BASE}`);
  await waitForCalibrationIdle();

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

  let current = "startup";
  try {
    await page.goto(BASE + "/", { waitUntil: "networkidle2", timeout: 120000 });
    await waitFor(page, () => !!document.querySelector('nav[aria-label="Workspaces"]'), "app shell");
    await waitFor(
      page,
      () => [...document.querySelectorAll("span")].some((s) => s.textContent.trim() === "LIVE"),
      "LIVE badge (backend reachable, not mock)",
    );
    await page.evaluate(() => document.fonts.ready);

    // --- Graph workspace: baseline lattice renders before any Run ----------
    current = "graph_load";
    await openWorkspace(page, "Universe", "Graph");
    await waitFor(
      page,
      () => document.querySelectorAll("main svg circle").length >= 10,
      "graph lattice nodes (baseline fits can take a while on first load)",
      300000,
    );
    await sleep(1500);

    // Propagation = Messages (the production default; set explicitly so the
    // capture is self-sufficient), Observations = From calibrations.
    current = "segments";
    await clickButton(page, "Messages");
    await clickButton(page, "From calibrations");

    // --- Run: the calibrations solve (drawer flips to Diagnostics) ----------
    current = "graph_extrapolate";
    await clickButton(page, "Run");
    await waitResultsRows(page);
    await sleep(8000); // BFS reveal wave + attribution particles
    await shotFull(page, "graph_extrapolate");

    current = "graph_lattice_content";
    await shotElement(page, "graph_lattice_content", () => {
      const h = [...document.querySelectorAll("main h2")].find(
        (h) => h.textContent.trim() === "Smile universe",
      );
      const card = h ? h.closest('[class*="rounded-xl"]') : null;
      if (!card) return false;
      card.setAttribute("data-shot-target", "1");
      return true;
    });

    // --- edge_editor: the "Message relations" policy editor -----------------
    current = "edge_editor";
    await clickButton(page, "Edges");
    await waitFor(
      page,
      () =>
        [...document.querySelectorAll("span")].some(
          (s) => s.textContent.trim() === "Message relations",
        ),
      "Message relations editor modal",
    );
    await clickButton(page, "Seed from auto relations");
    await waitFor(
      page,
      () => document.querySelectorAll("div.fixed select").length >= 10,
      "seeded message-relation rows (per-row class selects)",
    );
    await sleep(900);
    await shotElement(page, "edge_editor", () => {
      const s = [...document.querySelectorAll("span")].find(
        (s) => s.textContent.trim() === "Message relations",
      );
      const modal = s ? s.closest('[class*="rounded-xl"]') : null;
      if (!modal) return false;
      modal.setAttribute("data-shot-target", "1");
      return true;
    });
    await clickButton(page, "", { title: "Close" });
    await sleep(500);

    // --- graph_sandbox: unified what-if (Cross basket scenario) -------------
    current = "graph_sandbox";
    await clickButton(page, "Manual what-if");
    await sleep(400);
    // Drawer -> Preview tab (post-Run it sits on Diagnostics).
    await clickButton(page, "Preview");
    await waitFor(
      page,
      () =>
        [...document.querySelectorAll("button")].some(
          (b) => b.textContent.trim() === "Cross basket" && b.offsetParent !== null,
        ),
      "what-if scenario shortcuts",
    );
    await clickButton(page, "Cross basket");
    await sleep(600);
    await clickButton(page, "Run");
    await sleep(9000); // solve + reveal wave
    await shotFull(page, "graph_sandbox");

    // --- back to the calibrations solve for the hero node -------------------
    current = "hero_resolve";
    await clickButton(page, "From calibrations");
    await sleep(400);
    await clickButton(page, "Run");
    await waitResultsRows(page);
    await sleep(2500);

    // --- smile_hero: dark NVDA node's reconstructed smile -------------------
    // NB: the drawer is ALREADY on Diagnostics after a Run (auto-switch);
    // clicking the active tab again would collapse the drawer.
    current = "smile_hero";
    await sleep(500);
    const heroRow = await page.evaluate(() => {
      const rowText = (b) => {
        // climb a few ancestors to reach the full row (the button's immediate
        // div may be just the trailing control cluster)
        let el = b;
        for (let i = 0; i < 4 && el; i++) {
          if (el.textContent.includes("NVDA")) return el.textContent;
          el = el.parentElement;
        }
        return "";
      };
      const opens = [
        ...document.querySelectorAll('button[title="Open this node\'s reconstructed smile"]'),
      ].filter((b) => b.offsetParent !== null && rowText(b) !== "");
      if (opens.length === 0) return null;
      const target = opens[Math.floor(opens.length / 2)];
      const label = rowText(target).trim().slice(0, 60);
      target.click();
      return label;
    });
    if (heroRow === null) throw new Error("no NVDA row in the Diagnostics drawer");
    log(`opened hero node: ${heroRow}`);
    await waitFor(
      page,
      () =>
        [...document.querySelectorAll("span")].some((s) => s.textContent.trim() === "GRAPH") &&
        [...document.querySelectorAll("main svg path")].length >= 2,
      "GRAPH overlay badge + violet posterior curve",
      180000,
    );
    await sleep(1800); // band fill + error-bar settle
    await shotFull(page, "smile_hero");

    current = "smile_hero_wide";
    await shotElement(page, "smile_hero_wide", () => {
      const cards = [...document.querySelectorAll('main [class*="rounded-xl"]')];
      const el = cards.find((c) => c.querySelector("svg") && c.clientWidth > 900);
      if (!el) return false;
      el.setAttribute("data-shot-target", "1");
      return true;
    });

    // --- filter_smile: SPY smile with the filter posterior overlay ----------
    current = "filter_smile";
    await clickButton(page, "", { title: "Dismiss the graph-extrapolation overlay" });
    await sleep(400);
    await setSelect(page, { label: "Underlying" }, { value: "SPY" });
    await waitFor(
      page,
      () => {
        const lab = [...document.querySelectorAll("label")].find((l) =>
          l.textContent.trim().startsWith("Expiry"),
        );
        return !!lab && lab.querySelector("select").options.length >= 2;
      },
      "SPY expiry ladder",
    );
    await setSelect(page, { label: "Expiry" }, { index: 2 }); // the nudged expiry
    await waitFor(
      page,
      () => [...document.querySelectorAll("span")].some((s) => s.textContent.trim() === "FILTER"),
      "FILTER badge (observation filter active on SPY)",
      180000,
    );
    await sleep(1500);
    await shotFull(page, "filter_smile");

    // --- Options (brand menu): filter panel + prior-persistence card --------
    current = "filter_panel";
    await openBrandMenuItem(page, "Options");
    await waitFor(page, () => !!document.querySelector("#opt-filter"), "Options view (#opt-filter)");
    await page.evaluate(() => {
      document.querySelector("#opt-filter")?.scrollIntoView({ block: "center" });
    });
    await waitFor(
      page,
      () => document.querySelectorAll("#opt-filter table tbody tr").length >= 2,
      "filter diagnostics table rows",
      180000,
    );
    await sleep(900);
    await shotElement(page, "filter_panel", () => {
      const card = document.querySelector("#opt-filter");
      if (!card) return false;
      card.setAttribute("data-shot-target", "1");
      return true;
    });

    // --- options_calibration_crop: the Prior persistence card ---------------
    current = "options_calibration_crop";
    await page.evaluate(() => {
      document.querySelector("#opt-prior")?.scrollIntoView({ block: "center" });
    });
    await sleep(600);
    await shotElement(page, "options_calibration_crop", () => {
      const card = document.querySelector("#opt-prior");
      if (!card) return false;
      card.setAttribute("data-shot-target", "1");
      return true;
    });

    log("ALL GRAPH SHOTS DONE");
  } catch (err) {
    const dbg = path.join(SHOTS, `_debug_${current}.png`);
    try {
      await page.screenshot({ path: dbg });
      log(`FAILED at "${current}" — debug screenshot: ${dbg}`);
    } catch {
      /* page gone */
    }
    throw err;
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(`[capture_graph] FATAL: ${err.message ?? err}`);
  process.exit(1);
});

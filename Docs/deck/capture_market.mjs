// Deck screenshot capture — MARKET session (live Yahoo, staged by stage_market.py).
//
// Run from frontend\ (puppeteer-core is installed there):
//     node ..\Docs\deck\capture_market.mjs [http://127.0.0.1:8001]
//
// Drives headless Edge at 1920x1080 dsf 2, forces the LIGHT theme via
// localStorage before any page script runs, and writes PNGs into
// Docs\deck\assets\shots\. Fails loudly per shot; a failing shot dumps a
// _debug_<name>.png of whatever was on screen.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const BASE = (process.argv[2] ?? "http://127.0.0.1:8001").replace(/\/$/, "");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(HERE, "assets", "shots");

const log = (m) => console.log(`[capture_market] ${m}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- helpers
async function waitForCalibrationIdle(timeoutS = 300) {
  const deadline = Date.now() + timeoutS * 1000;
  for (;;) {
    const st = await (await fetch(`${BASE}/calibration/status`)).json();
    if (!st.running) {
      if (st.staleNodes > 0)
        log(`WARNING: ${st.staleNodes} stale nodes — run stage_market.py first for clean shots`);
      return st;
    }
    log(`  calibration running ${st.done}/${st.total} — waiting`);
    if (Date.now() > deadline) throw new Error("calibration never went idle");
    await sleep(2000);
  }
}

/** page.waitForFunction with a readable failure message. */
async function waitFor(page, fn, desc, timeout = 120000, ...args) {
  try {
    await page.waitForFunction(fn, { timeout, polling: 400 }, ...args);
  } catch {
    throw new Error(`timed out waiting for: ${desc}`);
  }
}

/** Click the workspace tab with this exact label (TopBar nav). */
async function clickTab(page, label) {
  const ok = await page.evaluate((label) => {
    const btns = [...document.querySelectorAll('nav[aria-label="Workspaces"] button')];
    const b = btns.find((b) => b.textContent.trim() === label);
    if (!b || b.disabled) return false;
    b.click();
    return true;
  }, label);
  if (!ok) throw new Error(`tab "${label}" not found or disabled`);
  log(`tab -> ${label}`);
  await sleep(500);
}

/** Click the first VISIBLE button whose trimmed text equals `text`. */
async function clickButton(page, text, { contains = false } = {}) {
  const ok = await page.evaluate(
    (text, contains) => {
      const btns = [...document.querySelectorAll("button")].filter(
        (b) => b.offsetParent !== null,
      );
      const b = btns.find((b) => {
        const t = b.textContent.trim();
        return contains ? t.includes(text) : t === text;
      });
      if (!b) return false;
      b.click();
      return true;
    },
    text,
    contains,
  );
  if (!ok) throw new Error(`button "${text}" not found`);
  log(`click -> ${text}`);
  await sleep(400);
}

/**
 * Set a React-controlled <select>. Finder: {label} = wrapped in a <label>
 * starting with that text (Underlying / Expiry), {title} = the select's own
 * title attribute, {css} = raw selector. Set by {value} or option {index}.
 */
async function setSelect(page, finder, { value = null, index = null } = {}) {
  const result = await page.evaluate(
    (finder, value, index) => {
      let sel = null;
      if (finder.css) sel = document.querySelector(finder.css);
      else if (finder.title) sel = document.querySelector(`select[title="${finder.title}"]`);
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
  const file = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: file });
  log(`SHOT ${name}.png (full viewport)`);
}

/**
 * Element-clipped shot. `markFn` runs in the page, finds the element and must
 * set data-shot-target="1" on it (return true on success).
 */
async function shotElement(page, name, markFn, ...args) {
  await page.evaluate((sel) => {
    document.querySelectorAll(sel).forEach((e) => e.removeAttribute("data-shot-target"));
  }, "[data-shot-target]");
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

/** Mark the main chart card: the first wide rounded card containing an <svg>. */
const markChartCard = () => {
  const cards = [...document.querySelectorAll('main [class*="rounded-xl"]')];
  const el = cards.find((c) => c.querySelector("svg") && c.clientWidth > 700);
  if (!el) return false;
  el.setAttribute("data-shot-target", "1");
  return true;
};

/** Wait until the active chart card holds >= n svg paths (chart rendered). */
async function waitChart(page, n = 1, timeout = 120000) {
  await waitFor(
    page,
    (n) => {
      const svgs = [...document.querySelectorAll("main svg")];
      const paths = svgs.reduce((c, s) => c + s.querySelectorAll("path").length, 0);
      return paths >= n;
    },
    `chart with >= ${n} svg paths`,
    timeout,
    n,
  );
  await sleep(1200); // settle: transitions, tick layout, band fills
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
  // LIGHT THEME before any app script runs (viewSettings reads this key).
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

    // Parametric, SPY, mid-dated expiry (~90d = 3rd of the 6 staged rungs).
    await setSelect(page, { label: "Underlying" }, { value: "SPY" });
    await waitFor(
      page,
      () => {
        const lab = [...document.querySelectorAll("label")].find((l) =>
          l.textContent.trim().startsWith("Expiry"),
        );
        return !!lab && lab.querySelector("select").options.length >= 2;
      },
      "expiry ladder populated",
    );
    await setSelect(page, { label: "Expiry" }, { index: 2 });
    await waitChart(page, 1);

    // --- quote_table: Parametric quote table (full viewport) ---------------
    current = "quote_table";
    await clickButton(page, "Table");
    await waitFor(
      page,
      () => document.querySelectorAll("main table tbody tr").length >= 5,
      "quote table rows",
    );
    await sleep(900);
    await shotFull(page, "quote_table");

    // --- montage clips BEFORE switching the axis mode to %ATM --------------
    current = "densities";
    await clickButton(page, "Densities");
    await waitChart(page, 3);
    await shotElement(page, "densities", markChartCard);

    current = "stacked_iv";
    await clickButton(page, "Stacked IV");
    await waitChart(page, 3);
    await shotElement(page, "stacked_iv", markChartCard);

    current = "logq";
    await clickButton(page, "Log Q-density");
    await waitChart(page, 1);
    await shotElement(page, "logq", markChartCard);

    current = "surface";
    await clickButton(page, "Surface");
    await waitChart(page, 6);
    await shotElement(page, "surface", markChartCard);

    // --- term: Term sub-tab (event calendar staged on SPY) -----------------
    current = "term";
    await clickButton(page, "Term");
    await waitChart(page, 2);
    await shotFull(page, "term");

    // --- parametric_smile: Smile view, x-axis in %ATM, aside visible -------
    current = "parametric_smile";
    await clickButton(page, "Smile");
    await waitChart(page, 1);
    await setSelect(page, { title: "Strike-axis display mode" }, { value: "pctatm" });
    await sleep(800);
    await shotFull(page, "parametric_smile");
    // restore the default axis so later sessions aren't surprised
    await setSelect(page, { title: "Strike-axis display mode" }, { value: "logmoneyness" });

    // --- Local Vol tab ------------------------------------------------------
    current = "localvol_smile";
    await clickTab(page, "Local Vol");
    // The LV fit can be slow on first open — wait for the reconstructed smile.
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
    await waitChart(page, 1, 420000);
    await shotFull(page, "localvol_smile");

    current = "localvol_heatmap";
    await clickButton(page, "LV surface");
    await waitFor(
      page,
      () =>
        document.querySelector("main canvas") !== null ||
        [...document.querySelectorAll("main svg")].some(
          (s) => s.querySelectorAll("rect").length > 10,
        ),
      "LV heatmap painted (rect cells)",
    );
    await sleep(1200);
    await shotFull(page, "localvol_heatmap");

    current = "localvol_ivsurface";
    await clickButton(page, "IV surface");
    await waitChart(page, 6);
    await shotElement(page, "localvol_ivsurface", markChartCard);

    // --- forwards -----------------------------------------------------------
    current = "forwards";
    await clickTab(page, "Forwards");
    await waitChart(page, 1);
    await shotFull(page, "forwards");

    // --- universe (montage clip of the tab content) --------------------------
    current = "universe";
    await clickTab(page, "Universe");
    await waitFor(
      page,
      () => [...document.querySelectorAll("main h2")].some((h) => h.textContent.includes("Add underlying")),
      "universe manager",
    );
    await sleep(1200);
    await shotElement(page, "universe", () => {
      const el = document.querySelector("main");
      if (!el) return false;
      el.setAttribute("data-shot-target", "1");
      return true;
    });

    // --- quality -------------------------------------------------------------
    current = "quality";
    await clickTab(page, "Quality");
    await waitFor(
      page,
      () => document.querySelectorAll("main table tbody tr").length >= 3,
      "quality exception table",
    );
    await sleep(900);
    await shotFull(page, "quality");

    // --- options: top (Model & hyperparameters) + Calibration card ----------
    current = "options_top";
    await clickTab(page, "Options");
    await waitFor(
      page,
      () => [...document.querySelectorAll("main h3")].some((h) => h.textContent.includes("Model & hyperparameters")),
      "options cards",
    );
    await page.evaluate(() => {
      document.querySelector("main").scrollTo(0, 0);
      const scroller = document.querySelector("main > div");
      if (scroller) scroller.scrollTo(0, 0);
    });
    await sleep(700);
    await shotFull(page, "options_top");

    current = "options_calibration";
    await page.evaluate(() => {
      const h = [...document.querySelectorAll("main h3")].find(
        (h) => h.textContent.trim() === "Calibration",
      );
      if (h) h.scrollIntoView({ block: "start" });
    });
    await sleep(700);
    await shotFull(page, "options_calibration");

    log("ALL MARKET SHOTS DONE");
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
  console.error(`[capture_market] FATAL: ${err.message ?? err}`);
  process.exit(1);
});

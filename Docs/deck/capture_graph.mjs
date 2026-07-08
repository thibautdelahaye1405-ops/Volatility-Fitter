// Deck screenshot capture — GRAPH + FILTER session (synthetic, staged by
// stage_graph.py against the same :8001 server).
//
// Run from frontend\ (puppeteer-core is installed there):
//     node ..\Docs\deck\capture_graph.mjs [http://127.0.0.1:8001]
//
// Shots: graph_extrapolate, graph_lattice_crop, edge_editor, graph_sandbox,
// smile_hero, filter_smile, filter_panel, options_calibration_crop.
//
// The Solver-panel eta/kappa/lambda/nu are seeded from the Options graph-prior
// defaults (stage_graph.py set eta 3.16 / lambda 0.1), but the CROSS-TICKER
// EDGE WEIGHT (30) is UI-only state — this script sets it in the Solver panel
// before pressing Propagate, so the UI solve matches the staged knobs.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const BASE = (process.argv[2] ?? "http://127.0.0.1:8001").replace(/\/$/, "");
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(HERE, "assets", "shots");

// Solver knobs (must match stage_graph.py KNOBS): eta slider is log10-scaled,
// so 10^1 = 10x (the slider max). Lambda slider is linear. Cross weight is a
// number input.
const ETA_SLIDER = "1";
const LAMBDA_SLIDER = "0.1";
const CROSS_WEIGHT = "100";

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

async function clickButton(page, text, { contains = false, title = null } = {}) {
  const ok = await page.evaluate(
    (text, contains, title) => {
      const btns = [...document.querySelectorAll("button")].filter(
        (b) => b.offsetParent !== null,
      );
      const b = btns.find((b) => {
        if (title !== null) return b.getAttribute("title") === title;
        const t = b.textContent.trim();
        return contains ? t.includes(text) : t === text;
      });
      if (!b) return false;
      b.click();
      return true;
    },
    text,
    contains,
    title,
  );
  if (!ok) throw new Error(`button "${title ?? text}" not found`);
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

/** Set a React-controlled <input> (range or number) found inside the element
 *  carrying `containerTitle` as its title attribute (SolverPanel rows). */
async function setInputByContainerTitle(page, containerTitle, value) {
  const ok = await page.evaluate(
    (containerTitle, value) => {
      const host = document.querySelector(`[title="${containerTitle}"]`);
      const input = host ? host.querySelector("input") : null;
      if (!input || input.offsetParent === null) return false;
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      ).set;
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    },
    containerTitle,
    value,
  );
  if (!ok) throw new Error(`input under [title="${containerTitle}"] not found`);
  log(`input [${containerTitle.slice(0, 40)}…] -> ${value}`);
  await sleep(300);
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

/** Toggle the "Solver settings" <details> in the Propagate panel. */
async function clickSolverSettings(page) {
  const ok = await page.evaluate(() => {
    const s = [...document.querySelectorAll("summary")].find(
      (s) => s.textContent.trim() === "Solver settings",
    );
    if (!s) return false;
    s.click();
    return true;
  });
  if (!ok) throw new Error('"Solver settings" summary not found');
  await sleep(400);
}

/** Wait for the Extrapolate results table (rows with lit/dark chips). */
async function waitResultsRows(page, minRows = 8, timeout = 300000) {
  await waitFor(
    page,
    (minRows) => {
      const chips = [...document.querySelectorAll("aside span")].filter((s) => {
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

    // --- Graph tab: baseline lattice (first load fits every node) ----------
    current = "graph_load";
    await clickTab(page, "Graph");
    await waitFor(
      page,
      () => document.querySelectorAll("main svg circle").length >= 10,
      "graph lattice nodes (baseline fits can take a while on first load)",
      300000,
    );
    await sleep(1500);

    // Solver knobs: eta + lambda should be pre-seeded from Options (staged),
    // but set all three explicitly so the capture is self-sufficient.
    current = "solver_knobs";
    await clickSolverSettings(page); // open
    await setInputByContainerTitle(
      page,
      "Directed-smoothness weight: how far an observation propagates.",
      ETA_SLIDER, // log10 slider: 0.5 -> 3.16x
    );
    await setInputByContainerTitle(
      page,
      "Optimal-transport flux weight; 0 disables the OT term.",
      LAMBDA_SLIDER,
    );
    await setInputByContainerTitle(
      page,
      "Weight of equal-expiry edges between tickers.",
      CROSS_WEIGHT,
    );
    await clickSolverSettings(page); // close for a clean panel

    // --- Propagate (From calibrations is the default source) ---------------
    current = "graph_extrapolate";
    await clickButton(page, "Propagate");
    await waitResultsRows(page);
    await sleep(8000); // let the BFS reveal wave + attribution particles play out
    await shotFull(page, "graph_extrapolate");

    current = "graph_lattice_crop";
    await shotElement(page, "graph_lattice_crop", () => {
      const h = [...document.querySelectorAll("main h2")].find(
        (h) => h.textContent.trim() === "Smile universe",
      );
      const card = h ? h.closest('[class*="rounded-xl"]') : null;
      if (!card) return false;
      card.setAttribute("data-shot-target", "1");
      return true;
    });

    // --- edge_editor: the Edges modal (matrix + per-edge overrides) --------
    current = "edge_editor";
    await clickButton(page, "Edges");
    await waitFor(
      page,
      () =>
        [...document.querySelectorAll("h3")].some((h) => h.textContent.trim() === "Edge weights") &&
        document.querySelectorAll("table tbody tr").length >= 3,
      "edge-weights matrix modal",
    );
    await sleep(900);
    await shotElement(page, "edge_editor", () => {
      const h = [...document.querySelectorAll("h3")].find(
        (h) => h.textContent.trim() === "Edge weights",
      );
      const modal = h ? h.closest('[class*="rounded-xl"]') : null;
      if (!modal) return false;
      modal.setAttribute("data-shot-target", "1");
      return true;
    });
    await clickButton(page, "", { title: "Close" });
    await sleep(500);

    // --- graph_sandbox: Manual what-if with a typed +2.0pt shift -----------
    current = "graph_sandbox";
    await clickButton(page, "Manual what-if");
    await waitFor(
      page,
      () =>
        [...document.querySelectorAll("aside input[type=number]")].filter(
          (i) => i.offsetParent !== null,
        ).length >= 1,
      "manual lit-node shift rows",
    );
    // First lit row: set the observation to +2.0 vol pts for a visible field.
    const setShift = await page.evaluate(() => {
      const input = [...document.querySelectorAll("aside .divide-y input[type=number]")].find(
        (i) => i.offsetParent !== null,
      );
      if (!input) return false;
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      ).set;
      setter.call(input, "2");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    });
    if (!setShift) throw new Error("manual shift input not found");
    await clickButton(page, "Propagate");
    await sleep(8000); // solve + reveal wave
    await shotFull(page, "graph_sandbox");

    // --- smile_hero: dark NVDA node's reconstructed smile ------------------
    current = "smile_hero";
    await clickButton(page, "From calibrations");
    await waitResultsRows(page); // the earlier extrapolation results persist
    const heroRow = await page.evaluate(() => {
      // Rows: aside entries with an ↗ open-smile button; pick the middle NVDA one.
      const opens = [...document.querySelectorAll(
        'button[title="Open this node\'s reconstructed smile"]',
      )].filter((b) => b.closest("div")?.textContent.includes("NVDA"));
      if (opens.length === 0) return null;
      const target = opens[Math.floor(opens.length / 2)];
      const label = target.closest("div")?.textContent.trim().slice(0, 60) ?? "?";
      target.click();
      return label;
    });
    if (heroRow === null) throw new Error("no NVDA row in the Extrapolate results panel");
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

    // --- filter_smile: SPY smile with the filter posterior overlay ---------
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
    await setSelect(page, { label: "Expiry" }, { index: 2 });
    await waitFor(
      page,
      () => [...document.querySelectorAll("span")].some((s) => s.textContent.trim() === "FILTER"),
      "FILTER badge (observation filter active on SPY)",
      180000,
    );
    await sleep(1500);
    await shotFull(page, "filter_smile");

    // --- filter_panel: Options -> Observation-filter section (element clip) -
    current = "filter_panel";
    await clickTab(page, "Options");
    await waitFor(
      page,
      () => [...document.querySelectorAll("main span")].some((s) => s.textContent.trim() === "Observation filter"),
      "observation-filter panel",
    );
    await page.evaluate(() => {
      const s = [...document.querySelectorAll("main span")].find(
        (s) => s.textContent.trim() === "Observation filter",
      );
      s?.scrollIntoView({ block: "center" });
    });
    await waitFor(
      page,
      () => {
        const s = [...document.querySelectorAll("main span")].find(
          (s) => s.textContent.trim() === "Observation filter",
        );
        const panel = s?.closest("div.border-t");
        return !!panel && panel.querySelectorAll("table tbody tr").length >= 2;
      },
      "filter diagnostics table rows",
      180000,
    );
    await sleep(900);
    await shotElement(page, "filter_panel", () => {
      const s = [...document.querySelectorAll("main span")].find(
        (s) => s.textContent.trim() === "Observation filter",
      );
      const panel = s ? s.closest("div.border-t") : null;
      if (!panel) return false;
      panel.setAttribute("data-shot-target", "1");
      return true;
    });

    // --- options_calibration_crop: the whole Calibration card --------------
    current = "options_calibration_crop";
    await shotElement(page, "options_calibration_crop", () => {
      const h = [...document.querySelectorAll("main h3")].find(
        (h) => h.textContent.trim() === "Calibration",
      );
      const card = h ? h.closest('[class*="rounded-xl"]') : null;
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

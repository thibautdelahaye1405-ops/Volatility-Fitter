// Deck screenshots of the STAGED VolFit demo instance (single-origin :8011 —
// 6 tickers, 39 lit LQD/haircut nodes, 8 dark nodes with real quotes, LV
// surfaces, auto message relations activated) plus two READ-ONLY shots of the
// user's live app (:5173 → the :8000 backend streaming a Massive book).
//
// Usage: cd frontend ; node scripts/demo_shots_graph.mjs [name-or-prefix ...]
//   no argument = every shot; `graph_` = the graph group; `lv_compare_smiles`.
//   DEMO_HIDE_NODES=1 hides the Nodes pane (Ctrl+B) on the graph shots.
// Output: Docs/deck/assets/shots_demo/<name>.png — light theme, 1600×1000 @2×.
//
// Writes on the staged instance are limited to what the brief allows: Run,
// the Layered/Precision segment, Compare operators (LOO), the Forwards lens's
// Joint carry checkbox, and (only if the preflight warns) the auto-relations
// reset + activate. Nothing is calibrated, saved, lit or darkened.
import { mkdirSync, writeFileSync } from "node:fs";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = "http://127.0.0.1:8011";
const LIVE = "http://localhost:5173";
const OUT = "C:\\Users\\thiba\\vol-fitter\\Docs\\deck\\assets\\shots_demo\\";
const DARK = "AAPL|2027-02-19";
const HIDE_NODES_PANE = process.env.DEMO_HIDE_NODES === "1";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const only = process.argv.slice(2);
const want = (name) => only.length === 0 || only.some((p) => name.startsWith(p));
const wantAny = (...names) => names.some((n) => want(n));

mkdirSync(OUT, { recursive: true });
const results = [];

// ---------------------------------------------------------------- helpers ---
async function api(method, path, body, base = BASE) {
  const r = await fetch(`${base}${path}`, {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function waitFor(page, fn, what, ms = 20000, arg) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn, arg)) return;
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${what}`);
}

async function newPage(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 2 });
  await page.evaluateOnNewDocument(() => {
    // LIGHT theme + the first-run Welcome already seen (Help Center flag).
    localStorage.setItem("volfit.viewSettings", JSON.stringify({ scheme: "light", contrast: 1, brightness: 1 }));
    localStorage.setItem("volfit.help.v1", JSON.stringify({ seenWelcome: true, tourDone: true, tourStep: 0, lastLink: "welcome" }));
  });
  page.on("pageerror", (e) => console.error(`  [pageerror] ${String(e).slice(0, 160)}`));
  return page;
}

async function themeCheck(page) {
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const m = /(\d+),\s*(\d+),\s*(\d+)/.exec(bg);
  const lum = m ? (Number(m[1]) + Number(m[2]) + Number(m[3])) / 3 : 0;
  if (lum < 128) throw new Error(`page is not in the light theme (body ${bg})`);
}

const full = (page, name) => page.screenshot({ path: OUT + name });

/** Rect (page coords) of an element: a CSS selector, or an in-page function
 *  body ("return …") that returns the element. */
async function rectOf(page, target, arg) {
  const rect = await page.evaluate(
    (t, a) => {
      const el = t.startsWith("return") ? new Function("arg", t)(a) : document.querySelector(t);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left, y: r.top, w: r.width, h: r.height };
    },
    target,
    arg,
  );
  if (!rect) throw new Error(`no element for ${String(target).slice(0, 70)}`);
  return rect;
}

async function crop(page, target, name, pad = 12, arg, maxWidth = Infinity) {
  const r = await rectOf(page, target, arg);
  const vp = page.viewport();
  const x = Math.max(0, r.x - pad);
  const y = Math.max(0, r.y - pad);
  const clip = { x, y, width: Math.min(vp.width - x, r.w + 2 * pad, maxWidth), height: Math.min(vp.height - y, r.h + 2 * pad) };
  if (clip.width < 20 || clip.height < 20) throw new Error(`degenerate crop ${JSON.stringify(clip)}`);
  await page.screenshot({ path: OUT + name, clip });
}

async function shot(name, fn) {
  if (!want(name)) return;
  try {
    const note = await fn();
    results.push({ name, ok: true, note: note ?? "" });
    console.log(`ok   ${name}${note ? ` — ${note}` : ""}`);
  } catch (err) {
    results.push({ name, ok: false, note: err.message });
    console.error(`FAIL ${name}: ${err.message}`);
  }
}

async function clickButtonText(page, label, scope = "main") {
  const ok = await page.evaluate(
    (l, s) => {
      const root = document.querySelector(s) ?? document;
      const b = [...root.querySelectorAll("button")].find((x) => x.textContent?.trim() === l && !x.disabled);
      if (!b) return false;
      b.click();
      return true;
    },
    label,
    scope,
  );
  if (!ok) throw new Error(`button "${label}" not found (enabled) in ${scope}`);
}

const mainText = (page) => page.evaluate(() => document.querySelector("main")?.innerText ?? "");
const squash = (s, n = 300) => s.replace(/\s+/g, " ").trim().slice(0, n);

async function gotoNode(page, node, activity) {
  await page.goto(`${BASE}/?node=${encodeURIComponent(node)}&activity=${activity}`, { waitUntil: "networkidle2", timeout: 60000 });
  await sleep(600);
  await page.keyboard.press("Escape"); // any stray dialog
  await sleep(300);
  await themeCheck(page);
}

// ------------------------------------------------------------------ graph ---
const GRAPH_SHOTS = [
  "graph_canvas_before", "graph_canvas_run", "graph_inspector_dark", "graph_drawer_diagnostics",
  "graph_relation_card", "graph_coupling_pane", "graph_precision_run", "graph_validation_loo",
  "graph_observation_plan", "graph_dark_smile", "graph_dark_smile_chart",
];

const runEnabled = () => [...document.querySelectorAll("button")].some((b) => b.textContent?.trim() === "Run" && !b.disabled);

async function runGraph(page) {
  await clickButtonText(page, "Run");
  // Run disables while solving; wait for the (brief) disable, then the settle.
  const t0 = Date.now();
  while (Date.now() - t0 < 4000) {
    if (!(await page.evaluate(runEnabled))) break;
    await sleep(100);
  }
  await waitFor(page, () => !!document.querySelector('[data-testid="run-summary"]'), "run summary", 120000);
  await waitFor(page, runEnabled, "Run settled", 120000);
  await sleep(4000); // the reveal wave + particles settle
  return page.evaluate(() => document.querySelector('[data-testid="run-summary"]')?.textContent?.trim() ?? "");
}

const DRAWER = "return document.querySelector('[data-testid=\"graph-drawer-body\"]')?.parentElement";

/** Show a drawer tab. Re-clicking the ACTIVE tab collapses the drawer, so the
 *  click is made only when the tab is inactive or the drawer is collapsed. */
async function openDrawerTab(page, label) {
  const state = await page.evaluate((l) => {
    const b = [...document.querySelectorAll("main button")].find((x) => x.textContent?.trim() === l);
    return { found: !!b, active: b?.className.includes("bg-surface-800") ?? false, open: !!document.querySelector('[data-testid="graph-drawer-body"]') };
  }, label);
  if (!state.found) throw new Error(`drawer tab "${label}" not found`);
  if (!(state.active && state.open)) await clickButtonText(page, label);
  await waitFor(page, () => !!document.querySelector('[data-testid="graph-drawer-body"]'), "the drawer body", 5000);
  await sleep(400);
}
const drawerText = (page) => page.evaluate(() => document.querySelector('[data-testid="graph-drawer-body"]')?.innerText ?? "");

async function graphShots(browser) {
  if (!wantAny(...GRAPH_SHOTS)) return;
  // Preflight on the mode the lens runs (message relations). A GET of a smile
  // in the viewed fit mode re-notes 'haircut' server-side (the mode the staged
  // fits were made in) before the dry run reads calibration presence.
  await api("GET", "/smiles/SPY/2026-12-18?fit_mode=haircut");
  let pf = await api("POST", "/graph/preflight", { propagationMode: "layered_dynamic_harmonic" });
  if (!pf.ok || pf.issues.some((i) => i.code === "no_lit_path")) {
    console.log(`preflight warned (${pf.issues.map((i) => i.code).join(", ")}) — resetting the auto relations`);
    const auto = await api("GET", "/graph/edges/messages/auto");
    await api("PUT", "/graph/edges/messages", { edges: auto.edges });
    await api("POST", "/graph/config/messages/activate", { notes: "demo" });
    pf = await api("POST", "/graph/preflight", { propagationMode: "layered_dynamic_harmonic" });
  }
  console.log(`preflight: ok=${pf.ok} lit ${pf.litCount} dark ${pf.darkCount} obs ${pf.observationCount} issues [${pf.issues.map((i) => i.code).join(", ")}]`);

  const page = await newPage(browser);
  await gotoNode(page, DARK, "graph");
  await waitFor(page, () => document.querySelectorAll('[data-testid="graph-canvas"] [data-node]').length > 10, "canvas nodes", 90000);
  await sleep(1500);
  if (HIDE_NODES_PANE) {
    await page.keyboard.down("Control"); await page.keyboard.press("KeyB"); await page.keyboard.up("Control");
    await sleep(800);
  }
  const counts = await page.evaluate(() => ({
    nodes: document.querySelectorAll('[data-testid="graph-canvas"] [data-node]').length,
    arrows: document.querySelectorAll("[data-calendar] polygon").length,
  }));

  await shot("graph_canvas_before.png", async () => {
    await full(page, "graph_canvas_before.png");
    return `${counts.nodes} nodes · ${counts.arrows} calendar arrow heads`;
  });

  let summary = "";
  await shot("graph_canvas_run.png", async () => {
    summary = await runGraph(page);
    await openDrawerTab(page, "Diagnostics");
    await full(page, "graph_canvas_run.png");
    return summary;
  });
  if (summary === "" && wantAny("graph_inspector_dark", "graph_drawer_diagnostics", "graph_observation_plan", "graph_dark_smile", "graph_relation_card")) {
    summary = await runGraph(page);
  }

  await shot("graph_inspector_dark.png", async () => {
    const c = await rectOf(page, `[data-testid="graph-canvas"] [data-node="${DARK}"] circle:last-of-type`);
    await page.mouse.click(c.x + c.w / 2, c.y + c.h / 2);
    await waitFor(page, () => (document.querySelector('[data-testid="inspector-pane"]')?.innerText ?? "").includes("Posterior confidence"), "inspector facts", 15000);
    await sleep(500);
    await crop(page, '[data-testid="inspector-pane"]', "graph_inspector_dark.png");
    return squash(await page.evaluate(() => document.querySelector('[data-testid="inspector-pane"]')?.innerText ?? ""), 420);
  });

  await shot("graph_drawer_diagnostics.png", async () => {
    await openDrawerTab(page, "Diagnostics");
    await crop(page, DRAWER, "graph_drawer_diagnostics.png");
    return squash(await drawerText(page));
  });

  await shot("graph_relation_card.png", async () => {
    const hop = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll('[data-testid="graph-canvas"] [data-node] circle:last-of-type')].map((c) => {
        const r = c.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, r: r.width / 2 };
      });
      const lines = [...document.querySelectorAll("[data-calendar] line")];
      const mid = (el) => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, len: Math.hypot(r.width, r.height) }; };
      const idOf = (el) => el.closest("[data-calendar]")?.getAttribute("data-calendar");
      for (let i = lines.length - 1; i >= 0; i--) {
        const m = mid(lines[i]);
        if (m.len < 12) continue;
        const clear = nodes.every((n) => Math.hypot(n.x - m.x, n.y - m.y) > n.r + 3);
        if (clear) return { ...m, id: idOf(lines[i]) };
      }
      const last = lines[lines.length - 1];
      return last ? { ...mid(last), id: idOf(last) } : null;
    });
    if (!hop) throw new Error("no clear calendar hop");
    await page.mouse.click(hop.x, hop.y);
    await waitFor(page, () => !!document.querySelector('[data-testid="relation-card"]'), "relation card", 10000);
    await sleep(500);
    // From the pane's top (the Inspector heading) down to the card's bottom.
    const pane = await rectOf(page, '[data-testid="inspector-pane"]');
    const card = await rectOf(page, '[data-testid="relation-card"]');
    await page.screenshot({ path: OUT + "graph_relation_card.png", clip: { x: pane.x - 12, y: pane.y - 12, width: pane.w + 24, height: card.y + card.h - pane.y + 24 } });
    const txt = await page.evaluate(() => document.querySelector('[data-testid="relation-card"]')?.innerText ?? "");
    await page.keyboard.press("Escape");
    await sleep(300);
    return `${hop.id} · ${squash(txt)}`;
  });

  await shot("graph_coupling_pane.png", async () => {
    const pane = await rectOf(page, '[data-testid="policy-pane"]');
    const last = await rectOf(page, "return document.querySelector('[data-testid=\"policy-pane\"]')?.lastElementChild");
    await page.screenshot({ path: OUT + "graph_coupling_pane.png", clip: { x: pane.x - 12, y: pane.y - 12, width: pane.w + 24, height: last.y + last.h - pane.y + 28 } });
    return squash(await page.evaluate(() => document.querySelector('[data-testid="policy-pane"]')?.innerText ?? ""));
  });

  await shot("graph_precision_run.png", async () => {
    await clickButtonText(page, "Precision");
    await sleep(1200); // the preflight debounce + re-render
    const s = await runGraph(page);
    await full(page, "graph_precision_run.png");
    await clickButtonText(page, "Layered");
    await sleep(1200);
    await runGraph(page); // leave the Layered posterior on screen for the rest
    return s;
  });

  await shot("graph_validation_loo.png", async () => {
    await openDrawerTab(page, "Validation");
    await clickButtonText(page, "Compare operators (LOO)");
    await sleep(1000);
    await waitFor(
      page,
      () => {
        const body = document.querySelector('[data-testid="graph-drawer-body"]');
        if (!body) return false;
        const scoring = [...body.querySelectorAll("button")].some((b) => /Scoring/.test(b.textContent ?? ""));
        return !scoring && body.querySelectorAll("table tbody tr").length >= 2;
      },
      "the LOO table",
      200000,
    );
    await sleep(500);
    const table = await rectOf(page, '[data-testid="graph-drawer-body"] table');
    const dr = await rectOf(page, DRAWER);
    await crop(page, DRAWER, "graph_validation_loo.png", 12, undefined, Math.max(table.x + table.w - dr.x + 80, 760) + 24);
    return squash(await drawerText(page), 420);
  });

  await shot("graph_observation_plan.png", async () => {
    await openDrawerTab(page, "Observation plan");
    // The ranking is on demand: the card's Rank button (closed form on the posterior).
    const ranked = await page.evaluate(() => {
      const body = document.querySelector('[data-testid="graph-drawer-body"]');
      const b = [...(body?.querySelectorAll("button") ?? [])].find((x) => /^(Rank|Re-rank)$/.test(x.textContent?.trim() ?? ""));
      if (!b || b.disabled) return false;
      b.click();
      return true;
    });
    if (!ranked) throw new Error("no Rank button (Run first?)");
    await waitFor(page, () => {
      const t = document.querySelector('[data-testid="graph-drawer-body"]')?.innerText ?? "";
      return !/Ranking…/.test(t) && (/Re-rank/.test(t) || /nothing to rank/.test(t));
    }, "the observation plan ranking", 60000);
    await sleep(600);
    await crop(page, DRAWER, "graph_observation_plan.png");
    return squash(await drawerText(page));
  });

  if (wantAny("graph_dark_smile")) {
    await gotoNode(page, DARK, "parametric");
    await waitFor(page, () => (document.querySelector("main")?.innerText ?? "").includes("INFERRED · GRAPH"), "the INFERRED · GRAPH badge", 40000);
    await sleep(1200);
    await shot("graph_dark_smile.png", async () => {
      await full(page, "graph_dark_smile.png");
      const t = await mainText(page);
      return (t.match(/[^\n]*(RMS|in-band|ζ)[^\n]*/g) ?? []).slice(0, 4).join(" | ").slice(0, 300);
    });
    await shot("graph_dark_smile_chart.png", async () => {
      await crop(page, "return document.querySelector('main [data-chart-card]')?.parentElement?.parentElement", "graph_dark_smile_chart.png");
    });
  }
  await page.close();
}

// -------------------------------------------------------------- local vol ---
const LV_SHOTS = ["lv_surface_3d", "lv_smile", "lv_iv_surface", "lv_stacked", "lv_compare_sheets", "lv_compare_difference", "lv_compare_smiles", "lv_diagnostics_card"];

async function lvShots(browser) {
  if (!wantAny(...LV_SHOTS)) return;
  const page = await newPage(browser);
  let node = "QQQ|2026-12-18";
  await gotoNode(page, node, "localvol");
  await waitFor(page, () => /PDE solves|No local-vol surface|Calibrate/.test(document.querySelector("main")?.innerText ?? ""), "the LV lens", 90000);
  if (/No local-vol surface yet/.test(await mainText(page))) {
    node = "AAPL|2026-12-18";
    console.log("QQQ has no LV fit — using AAPL");
    await gotoNode(page, node, "localvol");
    await waitFor(page, () => /PDE solves/.test(document.querySelector("main")?.innerText ?? ""), "the AAPL LV lens", 90000);
  }
  await sleep(1000);
  const badges = async () => {
    const t = await mainText(page);
    const m = t.match(/rms [\d.]+ · conv [\d.]+ · max [\d.]+ bp/);
    const solves = t.match(/\d+ PDE solves · price rms [\d.—]+ bp/);
    return [m?.[0], solves?.[0], /arb-free/.test(t) ? "arb-free" : ""].filter(Boolean).join(" · ");
  };

  await shot("lv_surface_3d.png", async () => {
    await clickButtonText(page, "LV surface");
    await waitFor(page, () => document.querySelectorAll("main svg.cursor-grab").length >= 1 || document.querySelectorAll("main canvas").length >= 1, "the 3D mesh", 30000);
    await sleep(1500);
    await full(page, "lv_surface_3d.png");
    return `${node} · ${await badges()}`;
  });
  await shot("lv_smile.png", async () => {
    await clickButtonText(page, "Smile");
    await sleep(1500);
    await full(page, "lv_smile.png");
    return await badges();
  });
  await shot("lv_diagnostics_card.png", async () => {
    await crop(page, '[data-aside-panel="diag"]', "lv_diagnostics_card.png");
    return squash(await page.evaluate(() => document.querySelector('[data-aside-panel="diag"]')?.innerText ?? ""));
  });
  await shot("lv_iv_surface.png", async () => {
    await clickButtonText(page, "IV surface");
    await waitFor(page, () => document.querySelectorAll("main svg.cursor-grab").length >= 1, "the IV mesh", 30000);
    await sleep(1500);
    await full(page, "lv_iv_surface.png");
  });
  await shot("lv_stacked.png", async () => {
    await clickButtonText(page, "Stacked IV");
    await sleep(1800);
    await full(page, "lv_stacked.png");
  });
  const strip = () => page.evaluate(() => (document.querySelector("main")?.innerText ?? "").match(/twin [^\n]*bp/)?.[0] ?? "");
  // The affine sheet and the Difference heatmap draw only when the frozen LV
  // fit sits on the compare lattice (else the card asks for a Calibrate, which
  // the brief forbids): pick the first fitted ticker whose lattice matches.
  let latticeOk = false;
  if (wantAny("lv_compare")) {
    const [tk] = node.split("|");
    for (const t of [...new Set([tk, "AAPL", "NVDA", "XOM"])]) {
      try {
        const c = await api("POST", `/fit/affine/${t}/compare`, { fitMode: "haircut" });
        console.log(`compare ${t}: lattice match ${c.affineLatticeMatches} · twin ${c.twinScore?.rmsBp?.toFixed(1)} · param ${c.parametricScore?.rmsBp?.toFixed(1)} bp`);
        if (c.affineLatticeMatches) {
          latticeOk = true;
          if (t !== tk) {
            node = `${t}|2026-12-18`;
            await gotoNode(page, node, "localvol");
            await waitFor(page, () => /PDE solves/.test(document.querySelector("main")?.innerText ?? ""), `the ${t} LV lens`, 90000);
            await sleep(800);
          }
          break;
        }
      } catch (err) { console.log(`compare ${t}: ${err.message.slice(0, 100)}`); }
    }
  }
  await shot("lv_compare_sheets.png", async () => {
    await clickButtonText(page, "Compare");
    await waitFor(page, () => /round trip [\d.]+ · [\d.]+ bp/.test(document.querySelector("main")?.innerText ?? ""), "the score strip", 60000);
    await clickButtonText(page, "Sheets");
    await waitFor(page, (n) => document.querySelectorAll("main svg.cursor-grab").length >= n, "the sheets", 30000, latticeOk ? 2 : 1);
    await sleep(1500);
    await full(page, "lv_compare_sheets.png");
    const n = await page.evaluate(() => document.querySelectorAll("main svg.cursor-grab").length);
    return `${node} · ${n} sheet(s)${latticeOk ? "" : " — affine sheet withheld (fit on another lattice)"} · ${await strip()}`;
  });
  await shot("lv_compare_difference.png", async () => {
    await clickButtonText(page, "Difference");
    await waitFor(page, () => /σ_loc twin − affine|sits on another lattice/.test(document.querySelector("main")?.innerText ?? ""), "the difference view", 30000);
    if (latticeOk) await waitFor(page, () => document.querySelectorAll("main [data-chart-card] svg rect").length >= 20, "the heatmap cells", 30000);
    await sleep(800);
    await full(page, "lv_compare_difference.png");
    if (!latticeOk) return `${node} · NO heatmap — the fit sits on another lattice (Calibrate needed)`;
    const legend = await page.evaluate(() => (document.querySelector("main")?.innerText ?? "").match(/[−+-]?\d+\.\d pt/g)?.slice(0, 2) ?? []);
    return legend.join(" … ");
  });
  await shot("lv_compare_smiles.png", async () => {
    await clickButtonText(page, "Smiles");
    await waitFor(page, () => document.querySelectorAll('main svg path[data-overlay="Dupire twin"]').length >= 1, "the twin overlay", 30000);
    await sleep(1000);
    await full(page, "lv_compare_smiles.png");
    const rows = await page.evaluate(() => document.querySelectorAll("main [data-chart-card] table tbody tr").length);
    return `${rows} score rows · ${await strip()}`;
  });
  await page.close();
}

// --------------------------------------------------------------- forwards ---
const FWD_SHOTS = ["forwards_xom", "forwards_xom_joint", "forwards_panel"];
const FWD_PANEL = "return [...document.querySelectorAll('main aside')].find((a) => a.querySelector('h3')?.textContent?.trim() === 'Forward')";

async function forwardsShots(browser) {
  if (!wantAny(...FWD_SHOTS)) return;
  const page = await newPage(browser);
  await gotoNode(page, "XOM|2026-12-18", "forwards");
  await waitFor(page, () => document.querySelectorAll("main table tbody tr").length >= 3, "the forward ladder", 60000);
  await sleep(1500);
  const ladder = () => page.evaluate(() => [...document.querySelectorAll("main table tbody tr")].map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent?.trim()).join(" | ")).join(" ; "));
  await shot("forwards_xom.png", async () => {
    await full(page, "forwards_xom.png");
    return (await ladder()).slice(0, 500);
  });
  await shot("forwards_xom_joint.png", async () => {
    const [box] = await page.$$('xpath/.//main//label[contains(normalize-space(), "Joint carry")]/input');
    if (!box) throw new Error("Joint carry checkbox not found");
    if (!(await box.evaluate((el) => el.checked))) await box.click();
    await waitFor(page, () => [...document.querySelectorAll("main table thead th")].some((th) => th.textContent?.trim() === "Joint"), "the Joint column", 15000);
    // The joint reads land asynchronously — wait until a row shows a bp read (or 30 s).
    const t0 = Date.now();
    while (Date.now() - t0 < 30000) {
      const has = await page.evaluate(() => {
        const ths = [...document.querySelectorAll("main table thead th")].map((th) => th.textContent?.trim());
        const j = ths.indexOf("Joint");
        return [...document.querySelectorAll("main table tbody tr")].some((tr) => /bp/.test(tr.children[j]?.textContent ?? ""));
      });
      if (has) break;
      await sleep(500);
    }
    await sleep(800);
    await full(page, "forwards_xom_joint.png");
    return (await ladder()).slice(0, 600);
  });
  await shot("forwards_panel.png", async () => {
    await crop(page, FWD_PANEL, "forwards_panel.png");
    return squash(await page.evaluate(() => [...document.querySelectorAll("main aside")].find((a) => a.querySelector("h3")?.textContent?.trim() === "Forward")?.innerText ?? ""));
  });
  await page.close();
}

// ------------------------------------------------------- live app (read) ---
const LIVE_SHOTS = ["live_market_pill_tooltip", "live_datasources_card"];
const PILL = 'header button[title*="Data source & as-of"]';

async function liveShots(browser) {
  if (!wantAny(...LIVE_SHOTS)) return;
  const page = await newPage(browser);
  await page.goto(`${LIVE}/`, { waitUntil: "load", timeout: 60000 });
  await waitFor(page, (sel) => !!document.querySelector(sel), "the market pill", 60000, PILL);
  await sleep(4000); // the data sources + stream health poll
  await page.keyboard.press("Escape");
  await sleep(300);
  await themeCheck(page);

  await shot("live_market_pill_tooltip.png", async () => {
    await page.hover(PILL);
    await sleep(400);
    // Native title tooltips are drawn by the browser chrome, never in a
    // headless capture: render the pill's title text as a tooltip element
    // under the pill (verbatim content, tooltip styling), then remove it.
    const info = await page.evaluate((sel) => {
      const pill = document.querySelector(sel);
      const title = pill?.getAttribute("title") ?? "";
      const r = pill.getBoundingClientRect();
      const tip = document.createElement("div");
      tip.id = "__demo_tooltip";
      tip.textContent = title;
      Object.assign(tip.style, {
        position: "fixed", left: `${Math.max(8, r.left)}px`, top: `${r.bottom + 6}px`, zIndex: 99999,
        maxWidth: "760px", whiteSpace: "pre-wrap", padding: "6px 8px", borderRadius: "4px",
        background: "#ffffff", color: "#111827", border: "1px solid #cbd5e1", boxShadow: "0 4px 14px rgba(0,0,0,0.18)",
        font: "11px/1.45 ui-monospace, Consolas, monospace",
      });
      document.body.appendChild(tip);
      const tr = tip.getBoundingClientRect();
      return { title, bottom: tr.bottom, stream: /Stream:/.test(title) };
    }, PILL);
    const h = Math.max(140, Math.ceil(info.bottom + 12));
    await page.screenshot({ path: OUT + "live_market_pill_tooltip.png", clip: { x: 0, y: 0, width: 1600, height: Math.min(h, 1000) } });
    await page.evaluate(() => document.getElementById("__demo_tooltip")?.remove());
    return `${info.stream ? "Stream lines present" : "NO Stream lines (the active source has no stream)"} · title: ${info.title.replace(/\n/g, " ⏎ ")}`;
  });

  await shot("live_datasources_card.png", async () => {
    await page.click(PILL);
    await waitFor(page, () => (document.querySelector('[role="dialog"]')?.innerText ?? "").includes("Data sources"), "the Data sources card", 15000);
    await sleep(1500); // a health poll inside the card
    await full(page, "live_datasources_card.png");
    const txt = await page.evaluate(() => {
      const dlg = document.querySelector('[role="dialog"]');
      const h = [...(dlg?.querySelectorAll("h2") ?? [])].find((x) => x.textContent?.trim() === "Data sources");
      return h?.parentElement?.innerText ?? dlg?.innerText ?? "";
    });
    return squash(txt, 700);
  });

  await shot("live_datasources_stream_tooltip.png", async () => {
    // The stream health lines (acked of subscribed, cap, msg/s, allocation)
    // are the title of the streaming source's health row in the card — the
    // pill carries them only when the ACTIVE source streams. Same rendering
    // as the pill tooltip: the title text as a tooltip element, then removed.
    if (!(await page.$('[role="dialog"]'))) {
      await page.click(PILL);
      await waitFor(page, () => (document.querySelector('[role="dialog"]')?.innerText ?? "").includes("Data sources"), "the Data sources card", 15000);
    }
    const SH = '[role="dialog"] [data-testid^="stream-health-"]';
    if (!(await page.$(SH))) throw new Error("no streaming source in the Data sources card");
    await page.hover(SH);
    await sleep(300);
    const info = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      const title = el.getAttribute("title") ?? "";
      const r = el.getBoundingClientRect();
      const tip = document.createElement("div");
      tip.id = "__demo_tooltip";
      tip.textContent = title;
      Object.assign(tip.style, {
        position: "fixed", left: `${r.left}px`, top: `${r.bottom + 4}px`, zIndex: 99999,
        maxWidth: "560px", whiteSpace: "pre-wrap", padding: "6px 8px", borderRadius: "4px",
        background: "#ffffff", color: "#111827", border: "1px solid #cbd5e1", boxShadow: "0 4px 14px rgba(0,0,0,0.18)",
        font: "11px/1.45 ui-monospace, Consolas, monospace",
      });
      document.body.appendChild(tip);
      const t = tip.getBoundingClientRect();
      const card = [...document.querySelectorAll('[role="dialog"] h2')].find((h) => h.textContent?.trim() === "Data sources")?.parentElement?.getBoundingClientRect();
      return { title, tip: { x: t.left, y: t.top, w: t.width, h: t.height }, card: card && { x: card.left, y: card.top, w: card.width, h: card.height } };
    }, SH);
    const c = info.card ?? info.tip;
    const x = Math.max(0, Math.min(c.x, info.tip.x) - 12);
    const y = Math.max(0, c.y - 12);
    const right = Math.min(1600, Math.max(c.x + c.w, info.tip.x + info.tip.w) + 12);
    const bottom = Math.min(1000, Math.max(c.y + c.h, info.tip.y + info.tip.h) + 12);
    await page.screenshot({ path: OUT + "live_datasources_stream_tooltip.png", clip: { x, y, width: right - x, height: bottom - y } });
    await page.evaluate(() => document.getElementById("__demo_tooltip")?.remove());
    return info.title.replace(/\n/g, " ⏎ ");
  });
  await page.keyboard.press("Escape");
  await page.close();
}

// ------------------------------------------------------------------- main ---
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-first-run", "--disable-gpu"] });
try {
  await graphShots(browser);
  await lvShots(browser);
  await forwardsShots(browser);
  await liveShots(browser);
} finally {
  await browser.close();
}
const SMOKE = "C:/Users/thiba/vol-fitter/frontend/.smoke/";
mkdirSync(SMOKE, { recursive: true });
writeFileSync(SMOKE + "demo_shots_last_run.json", JSON.stringify(results, null, 2)); // the run log stays out of the deck folder
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} shots ok${failed.length ? ` — failed: ${failed.map((f) => f.name).join(", ")}` : ""}`);
process.exit(failed.length ? 1 : 0);

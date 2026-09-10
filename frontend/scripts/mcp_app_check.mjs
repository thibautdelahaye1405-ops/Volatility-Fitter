// Headless-Edge check of the MCP connector's inline chart apps (volfit_mcp/ui):
// a harness page plays the MCP Apps HOST (ext-apps 2026-01-26 postMessage
// protocol) — it answers ui/initialize, waits for ui/notifications/initialized,
// sends ui/notifications/tool-result with the recorded fixture, records every
// message the app sends back (size-changed, ui/message, tools/call) — and the
// script drives the app's own controls, screenshotting each state:
//   lv-compare: 3D affine, heatmap twin, difference, dark theme, rms-bar click
//   smile:      light, strike axis, dark, next-expiry (tools/call round trip)
//   surface:    3D + ATM ridge, heatmap full wings, strike axis, Workbench link
//   term:       vol + variance, event clock, point click -> chat message, dark
//   series:     bands + one trace per lane, expiry select, slider, next-frame
//               (tools/call series_frame round trip), dark, Workbench link
// No server needed: the app HTML is rendered by the Python package (Plotly
// inlined from backend/.cache, else the CDN). Screenshots in .smoke/mcp-*.png. Prereqs:
// ../.venv (mcp installed), Edge, puppeteer-core (npm i --no-save puppeteer-core).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const winPath = (u) => u.pathname.replace(/^\/(\w:)/, "$1");
const OUT = winPath(new URL("../.smoke/", import.meta.url));
const PY = winPath(new URL("../../.venv/Scripts/python.exe", import.meta.url));
const FIX = winPath(new URL("../../backend/tests/fixtures/", import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
if (!existsSync(PY)) throw new Error("needs ../.venv");
mkdirSync(OUT, { recursive: true });

// 1. The app pages exactly as the server serves them (bridge inlined).
const pages = JSON.parse(execFileSync(PY, ["-c", `
import json
from volfit_mcp.tools_charts import _html
print(json.dumps({"lv": _html("lv_compare.html"), "smile": _html("smile.html"), "surface": _html("vol_surface.html"), "term": _html("term.html"), "series": _html("series.html")}))
`], { encoding: "utf-8", cwd: winPath(new URL("../../backend/", import.meta.url)), maxBuffer: 64 * 1024 * 1024 }));  // the pages inline Plotly (~6 MB)
const seriesFx = JSON.parse(readFileSync(FIX + "mcp_series_frame.json", "utf-8"));  // frame 2 + frame 3 of a recorded series
const fixtures = {
  lv: JSON.parse(readFileSync(FIX + "mcp_lv_compare.json", "utf-8")),
  smile: JSON.parse(readFileSync(FIX + "mcp_smile.json", "utf-8")),
  surface: JSON.parse(readFileSync(FIX + "mcp_vol_surface.json", "utf-8")),
  term: JSON.parse(readFileSync(FIX + "mcp_term.json", "utf-8")),
  series: seriesFx.frame2,
  seriesNext: seriesFx.frame3,
};

// 2. The host harness: one sandboxed iframe (srcdoc) + the protocol.
const harness = (appHtml, theme) => `<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:${theme === "dark" ? "#111" : "#f4f4f5"}} iframe{border:0;width:960px;height:720px;display:block}
</style></head><body><iframe id="app" sandbox="allow-scripts"></iframe><script>
window.__msgs = []; window.__ready = false; window.__theme = ${JSON.stringify(theme)};
const frame = document.getElementById("app");
function send(m) { frame.contentWindow.postMessage(m, "*"); }
window.addEventListener("message", (ev) => {
  const m = ev.data; if (!m || m.jsonrpc !== "2.0") return;
  window.__msgs.push(m);
  if (m.method === "ui/initialize") {
    // Validate like the ext-apps host schema: appInfo + appCapabilities + protocolVersion.
    const p = m.params || {};
    if (!p.appInfo || !p.appInfo.name || !p.appCapabilities || typeof p.protocolVersion !== "string") {
      window.__initError = "ui/initialize params invalid: " + JSON.stringify(p);
      send({ jsonrpc: "2.0", id: m.id, error: { code: -32602, message: window.__initError } });
      return;
    }
    send({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2026-01-26",
      hostCapabilities: { serverTools: {}, openLinks: {} }, hostInfo: { name: "harness", version: "0" },
      hostContext: { theme: window.__theme, displayMode: "inline", containerDimensions: { width: 960, maxHeight: 900 }, locale: "en-US" } } });
  } else if (m.method === "ui/notifications/initialized") {
    window.__ready = true;
  } else if (m.method === "tools/call") {          // the smile app's prev/next expiry, the series app's next frame
    const fx = window.__fixture; const args = m.params.arguments || {};
    const alt = m.params.name === "series_frame" ? window.__fixtureNext : Object.assign({}, fx, { expiry: args.expiry, T: fx.T * 2 });
    send({ jsonrpc: "2.0", id: m.id, result: { content: [{ type: "text", text: "ok" }], structuredContent: alt } });
  } else if (m.method === "ui/message" || m.method === "ui/request-display-mode" || m.method === "ui/open-link") {
    send({ jsonrpc: "2.0", id: m.id, result: m.method === "ui/request-display-mode" ? { mode: m.params.mode } : {} });
  }
});
window.__deliver = (fixture, args, next) => {
  window.__fixture = fixture; window.__fixtureNext = next || null;
  send({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: args } });
  send({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { content: [{ type: "text", text: "summary" }], structuredContent: fixture } });
};
window.__setTheme = (t) => send({ jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: { theme: t } });
frame.srcdoc = ${JSON.stringify(appHtml).replace(/<\//g, "<\\/")};
</script></body></html>`;  // "<\/" keeps the app's own </script> tags from closing the harness script

const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok, detail }); console.log(`${ok ? "PASS" : "FAIL"} ${name} ${detail}`); };

async function openApp(browser, key, theme) {
  const page = await browser.newPage();
  await page.setViewport({ width: 980, height: 760, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => console.error("page error:", e.message));
  const file = OUT + `_mcp_harness_${key}_${theme}.html`;
  writeFileSync(file, harness(pages[key], theme));
  await page.goto("file:///" + file.replace(/\\/g, "/"), { waitUntil: "load" });
  await page.waitForFunction(() => window.__ready === true || window.__initError, { timeout: 30000 });
  const initError = await page.evaluate(() => window.__initError || null);
  check(`${key}: ui/initialize params valid`, !initError, initError || "");
  if (initError) throw new Error(initError);
  const args = key === "lv" ? { tickers: ["SPY"] } : key === "series" ? { id: fixtures.series.seriesId, frame: 2 } : { ticker: "SPY", expiry: fixtures.smile.expiry };
  await page.evaluate((fx, a, next) => window.__deliver(fx, a, next), fixtures[key], args, fixtures[key + "Next"] || null);
  const frame = page.frames().find((f) => f !== page.mainFrame());
  await frame.waitForFunction(() => document.querySelectorAll(".js-plotly-plot .plot-container").length > 0, { timeout: 40000 });
  await sleep(800);
  return { page, frame };
}
const shot = (page, name) => page.screenshot({ path: OUT + `mcp-${name}.png` });
const msgs = (page, method) => page.evaluate((m) => window.__msgs.filter((x) => x.method === m).length, method);

const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new", args: ["--no-sandbox", "--allow-file-access-from-files"] });
try {
  // ---- Local Vol compare
  let { page, frame } = await openApp(browser, "lv", "light");
  let plots = await frame.evaluate(() => document.querySelectorAll(".js-plotly-plot .plot-container").length);
  check("lv: main + rms plots rendered", plots === 2, `plots=${plots}`);
  check("lv: size-changed sent", (await msgs(page, "ui/notifications/size-changed")) > 0);
  check("lv: 3D surface trace", await frame.evaluate(() => !!document.querySelector("#main .gl-container canvas")));
  await shot(page, "lv-3d-affine");
  await frame.click("[data-layer=twin]"); await frame.click("[data-view=heat]"); await sleep(600);
  check("lv: heatmap twin", await frame.evaluate(() => !!document.querySelector("#main .heatmaplayer")));
  await shot(page, "lv-heat-twin");
  await frame.click("[data-layer=diff]"); await sleep(600);
  await shot(page, "lv-heat-diff");
  await page.evaluate(() => window.__setTheme("dark")); await sleep(600);
  check("lv: dark theme applied", (await frame.evaluate(() => document.documentElement.getAttribute("data-theme"))) === "dark");
  await shot(page, "lv-dark");
  const bars = await frame.$$("#rms .bars .point path");
  if (bars.length) { await bars[0].click(); await sleep(300); }
  check("lv: rms bar click -> ui/message", (await msgs(page, "ui/message")) > 0, `bars=${bars.length}`);
  await page.close();

  // ---- Smile viewer
  ({ page, frame } = await openApp(browser, "smile", "light"));
  const title = await frame.$eval("#title", (el) => el.textContent);
  check("smile: title carries ticker/expiry", title.includes("SPY") && title.includes(fixtures.smile.expiry), title);
  const tiles = await frame.$$eval(".tile", (els) => els.length);
  check("smile: diagnostic tiles", tiles >= 6, `tiles=${tiles}`);
  const traces = await frame.evaluate(() => document.querySelectorAll("#plot .scatterlayer .trace").length);
  check("smile: quotes + fit (+prior/LV) traces", traces >= 2, `traces=${traces}`);
  await shot(page, "smile-light");
  await frame.click("[data-axis=strike]"); await sleep(400);
  check("smile: strike axis", (await frame.$eval("[data-axis=strike]", (el) => el.className)).includes("on"));
  await shot(page, "smile-strike");
  await frame.click("#next"); await sleep(600);
  check("smile: next expiry -> tools/call round trip", (await msgs(page, "tools/call")) > 0);
  const title2 = await frame.$eval("#title", (el) => el.textContent);
  check("smile: title updated after round trip", title2 !== title, title2);
  await page.evaluate(() => window.__setTheme("dark")); await sleep(500);
  await shot(page, "smile-dark");
  check("smile: Workbench button shown", await frame.$eval("#wb", (el) => !el.hidden));
  await page.close();

  // ---- Series frame
  ({ page, frame } = await openApp(browser, "series", "light"));
  const sTitle = await frame.$eval("#title", (el) => el.textContent);
  check("series: title carries name + frame i/n", sTitle.includes("SPY") && sTitle.includes("frame 3/6"), sTitle);
  const sTraces = await frame.evaluate(() => document.querySelectorAll("#plot .scatterlayer .trace").length);
  check("series: bands + one trace per lane", sTraces >= 1 + fixtures.series.laneOrder.length, `traces=${sTraces}`);
  const legend = await frame.$eval("#legend", (el) => el.textContent);
  check("series: legend carries the per-lane rms", legend.includes("bp") && legend.includes("free"), legend);
  const opts = await frame.$$eval("#expiry option", (els) => els.length);
  check("series: expiry select lists the frame's expiries", opts === fixtures.series.frame.expiries.length, `options=${opts}`);
  check("series: slider spans the frames", (await frame.$eval("#slider", (el) => el.max)) === String(fixtures.series.nFrames - 1));
  await shot(page, "series-light");
  await frame.click("#next"); await sleep(600);
  const sCalls = await page.evaluate(() => window.__msgs.filter((x) => x.method === "tools/call" && x.params.name === "series_frame").length);
  check("series: next frame -> tools/call series_frame", sCalls > 0, `calls=${sCalls}`);
  const sTitle2 = await frame.$eval("#title", (el) => el.textContent);
  check("series: title updated after round trip", sTitle2.includes("frame 4/6"), sTitle2);
  await shot(page, "series-next");
  await page.evaluate(() => window.__setTheme("dark")); await sleep(500);
  check("series: dark theme applied", (await frame.evaluate(() => document.documentElement.getAttribute("data-theme"))) === "dark");
  await shot(page, "series-dark");
  await frame.click("#wb"); await sleep(200);
  check("series: Workbench -> ui/open-link", (await msgs(page, "ui/open-link")) > 0);
  await page.close();

  // ---- Implied-vol surface
  ({ page, frame } = await openApp(browser, "surface", "light"));
  check("surface: 3D surface + ATM ridge", await frame.evaluate(() => !!document.querySelector("#plot .gl-container canvas")));
  await shot(page, "surface-3d");
  await frame.click("[data-view=heat]"); await frame.click("[data-crop=full]"); await sleep(600);
  check("surface: heatmap full wings", await frame.evaluate(() => !!document.querySelector("#plot .heatmaplayer")));
  await shot(page, "surface-heat");
  await frame.click("[data-axis=strike]"); await frame.click('[data-view="3d"]'); await sleep(700);
  check("surface: strike axis in 3D", (await frame.$eval("[data-axis=strike]", (el) => el.className)).includes("on"));
  await frame.click("#wb"); await sleep(200);
  check("surface: Workbench -> ui/open-link", (await msgs(page, "ui/open-link")) > 0);
  await page.close();

  // ---- Term structure
  ({ page, frame } = await openApp(browser, "term", "light"));
  const termTraces = await frame.evaluate(() => document.querySelectorAll("#plot .scatterlayer .trace").length);
  check("term: vol + variance traces", termTraces >= 5, `traces=${termTraces}`);
  const termTiles = await frame.$$eval(".tile", (els) => els.length);
  check("term: tiles", termTiles >= 6, `tiles=${termTiles}`);
  await shot(page, "term-both");
  await frame.click("[data-clock=tau]"); await frame.click("[data-view=var]"); await sleep(500);
  check("term: variance-only on the event clock", (await frame.$eval("[data-view=var]", (el) => el.className)).includes("on"));
  await shot(page, "term-variance-tau");
  const pts = await frame.$$("#plot .scatterlayer .points path");
  if (pts.length) { await pts[0].click(); await sleep(300); }
  check("term: point click -> ui/message", (await msgs(page, "ui/message")) > 0, `points=${pts.length}`);
  await page.evaluate(() => window.__setTheme("dark")); await sleep(400);
  await shot(page, "term-dark");
  await page.close();
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed; screenshots in ${OUT}mcp-*.png`);
if (failed.length) process.exit(1);

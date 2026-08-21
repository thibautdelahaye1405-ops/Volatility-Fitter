// One-off research probe: what does the Euronext options page REALLY send when
// maturities / "all strikes" are selected? Drives the page's own
// refreshOptionsPrices() and records the XHR (url, headers, postData, result).
import puppeteer from "puppeteer-core";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const url = process.argv[2] || "https://live.euronext.com/en/product/index-options/AEX-DAMS";
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-sandbox", "--disable-gpu", "--lang=en-US"] });
const page = await browser.newPage();
await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0");
page.on("request", (req) => {
  if (/getPricesOptions/.test(req.url())) {
    console.log("REQ", req.method(), req.url());
    console.log("    headers:", JSON.stringify(Object.fromEntries(Object.entries(req.headers()).filter(([k]) => /^(content-type|x-requested-with|accept$|cookie|origin)/i.test(k)))).slice(0, 400));
    console.log("    postData:", String(req.postData()).slice(0, 400));
  }
});
page.on("response", async (res) => {
  if (/getPricesOptionsAjax/.test(res.url())) {
    try {
      const j = JSON.parse(await res.text());
      console.log("RESP", res.status(), "simple:", JSON.stringify(j.simple.map((e) => [e.maturityDate, e.data.length])));
    } catch (e) { console.log("RESP parse fail", String(e).slice(0, 80)); }
  }
});
await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((r) => setTimeout(r, 4000));
const info = await page.evaluate(() => {
  const sel = document.querySelector("#maturityDates");
  const opts = sel ? [...sel.options].map((o) => [o.value, o.text.trim(), o.selected]) : null;
  const shows = [...document.querySelectorAll("input[name='show']")].map((i) => [i.id, i.value, i.checked]);
  const ds = window.drupalSettings && window.drupalSettings.custom ? { class_symbol: drupalSettings.custom.class_symbol, class_exchange: drupalSettings.custom.class_exchange, param_options: drupalSettings.custom.param_options, type_for_url: drupalSettings.custom.contract && drupalSettings.custom.contract.type_for_url } : null;
  return { opts, shows, ds, hasRefresh: typeof refreshOptionsPrices, jq: typeof jQuery };
});
console.log("page state:", JSON.stringify(info).slice(0, 900));
// 1) select Dec 2026 + Sep 2026 and "all strikes", then call the page's own refresh
await page.evaluate(() => {
  const sel = document.querySelector("#maturityDates");
  if (sel) for (const o of sel.options) o.selected = ["01-09-2026", "01-12-2026"].includes(o.value);
  const all = document.querySelector("#show2");
  if (all) all.checked = true;
  if (window.jQuery) { jQuery("#maturityDates").trigger("change"); }
  if (typeof refreshOptionsPrices === "function") refreshOptionsPrices();
});
await new Promise((r) => setTimeout(r, 5000));
// 2) what does jQuery.param produce for the same data object?
const param = await page.evaluate(() => window.jQuery ? jQuery.param({ md: jQuery("#maturityDates").val(), ps: jQuery("input[name='show']:checked").val() }) : "no jQuery");
console.log("jQuery.param:", param);
// 3) a direct in-page ajax with explicit data, awaiting the result
const direct = await page.evaluate(() => new Promise((resolve) => {
  jQuery.ajax({ type: "POST", dataType: "json", data: { md: ["01-12-2026"], ps: "999" },
    url: "/en/ajax/getPricesOptionsAjax/index-options/AEX/DAMS",
    success: (d) => resolve(JSON.stringify(d.simple.map((e) => [e.maturityDate, e.data.length]))),
    error: (x) => resolve("ERR " + x.status) });
}));
console.log("in-page direct ajax (md Dec, ps 999):", direct);
await browser.close();

// Render the HTML deck, inspect layout and exercise its offline navigation.
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const root = path.resolve(import.meta.dirname, "../..");
const deck = process.argv[2] ?? path.join(root, "demo_deck.html");
const out = process.argv[3] ?? path.resolve(root, "../../tmp/demo_rewrite/render");
fs.mkdirSync(out, {recursive: true});
const browser = await puppeteer.launch({
  executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  headless: true,
  pipe: true,
  timeout: 60000,
  userDataDir: path.join(out, "browser-profile"),
  args: ["--no-first-run", "--disable-extensions", "--allow-file-access-from-files", "--disable-gpu"],
});
try {
  const page = await browser.newPage();
  await page.setViewport({width:1920, height:1080, deviceScaleFactor:1});
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("file:///" + deck.replaceAll("\\", "/"), {waitUntil:"networkidle0", timeout:120000});
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
  });
  const n = await page.evaluate(() => document.querySelectorAll(".slide").length);
  const results=[];
  for(let i=0;i<n;i++){
    await page.evaluate(i => {
      if(typeof show === "function") show(i);
      else document.querySelectorAll(".slide").forEach((s,j)=>s.classList.toggle("active",i===j));
    },i);
    const result=await page.evaluate(()=>{
      const s=document.querySelector(".slide.active"), r=s.getBoundingClientRect();
      const content=s.querySelector(".body"), cr=content?.getBoundingClientRect();
      const footer=s.querySelector(".foot"), fr=footer?.getBoundingClientRect();
      const problems=[];
      for(const el of s.querySelectorAll("h1,.lede,ul.points li,.strip,table,.shot,.figcard,.eq,.demo")){
        const q=el.getBoundingClientRect();
        if(q.left<r.left-1||q.right>r.right+1||q.bottom>r.bottom+1)
          problems.push("outside canvas: "+el.tagName);
        if(el.closest(".body") && fr && q.bottom>fr.top-8)
          problems.push("content intersects footer: "+el.tagName);
        if(el.closest(".body") && cr && q.top<cr.top-2)
          problems.push("content above allocated area: "+el.tagName);
      }
      const broken=[...s.querySelectorAll("img")].filter(im=>!im.complete||!im.naturalWidth).length;
      const t=s.querySelector("h1").textContent;
      return {title:t,problems,broken};
    });
    results.push({slide:i+1,...result});
    await page.screenshot({path:path.join(out,"slide-"+String(i+1).padStart(2,"0")+".png")});
  }
  if(await page.$("#contents")){
    await page.keyboard.press("Home");
    await page.keyboard.press("ArrowRight");
    const afterArrow=await page.$eval(".slide.active h1",e=>e.textContent);
    if(afterArrow!==results[1].title)errors.push("Arrow navigation failed");
    await page.keyboard.press("n");
    if(!await page.$eval("body",e=>e.classList.contains("notes-on")))errors.push("Notes toggle failed");
    await page.screenshot({path:path.join(out,"notes-preview.png")});
    await page.keyboard.press("Escape");
    await page.keyboard.press("o");
    if(!await page.$eval("#contents",e=>e.classList.contains("open")))errors.push("Contents toggle failed");
    await page.click("#contents ol li:last-child button");
    if(await page.$eval(".slide.active h1",e=>e.textContent)!==results.at(-1).title)errors.push("Contents selection failed");
    if(await page.$eval("#contents",e=>e.classList.contains("open")))errors.push("Contents did not close after selection");
    await page.evaluate(()=>{location.hash="#17"});
    await page.waitForFunction(()=>document.querySelector(".slide.active .foot span:last-child")?.textContent.startsWith("17 /"));
    if(await page.$eval(".slide.active h1",e=>e.textContent)!==results[16].title)errors.push("Direct slide link failed");
    await page.keyboard.press("Escape");
    await page.setViewport({width:1280,height:720,deviceScaleFactor:1});
    await page.keyboard.press("End");
    await page.screenshot({path:path.join(out,"projector-preview.png")});
    await page.setViewport({width:1920,height:1080,deviceScaleFactor:1});
    await page.keyboard.press("Home");
    const external=await page.evaluate(()=>[...document.querySelectorAll("img,script,link")].map(e=>e.src||e.href).filter(x=>/^https?:/.test(x)));
    if(external.length)errors.push("External resources: "+external.join(","));
  }
  fs.writeFileSync(path.join(out,"layout-report.json"),JSON.stringify({slides:n,errors,results},null,2));
  console.log(JSON.stringify({slides:n,errors,issues:results.filter(r=>r.problems.length||r.broken)},null,2));
  if(errors.length||results.some(r=>r.problems.length||r.broken))process.exitCode=1;
  if(process.argv.includes("--pdf")){
    await page.pdf({path:path.join(root,"demo_deck.pdf"),width:"1920px",height:"1080px",printBackground:true,timeout:180000});
    console.log("Updated demo_deck.pdf");
  }
}finally{await browser.close()}

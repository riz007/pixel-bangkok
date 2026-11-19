// Render the Open Graph card (1200x630) in a headless browser so Thai text is shaped correctly.
// Usage: node scripts/make-og.mjs <map.png> [out=public/og.jpg]
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { chromium } from "@playwright/test";

const [mapPath, out = "public/og.jpg"] = process.argv.slice(2);
if (!mapPath) throw new Error("usage: node scripts/make-og.mjs <map.png> [out]");
const map = `data:image/png;base64,${readFileSync(mapPath).toString("base64")}`;

const html = `<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Chonburi&family=Bai+Jamjuree:wght@500;600&display=block" rel="stylesheet">
<style>
  html, body { margin: 0; width: 1200px; height: 630px; background: #1c1412; overflow: hidden; }
  .map { position: absolute; inset: -40px -60px -10px -60px; background: url(${map}) center 60% / cover no-repeat; image-rendering: auto; }
  .shade { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(28,20,18,.92) 0%, rgba(28,20,18,.55) 34%, rgba(28,20,18,0) 58%); }
  .plate { position: absolute; left: 56px; top: 64px; padding: 22px 30px 18px; background: #1c1412;
           border: 3px solid #d4a53a; box-shadow: inset 0 0 0 6px #1c1412, inset 0 0 0 8px #9c7a2c; }
  .th { font-family: Chonburi; font-size: 62px; line-height: 1.25; color: #d4a53a; }
  .en { font-family: "Bai Jamjuree"; font-weight: 600; font-size: 30px; letter-spacing: 0.08em; color: #f3ead6; }
  .lede { position: absolute; left: 60px; top: 300px; width: 470px; font-family: "Bai Jamjuree";
          font-weight: 500; font-size: 28px; line-height: 1.35; color: #f3ead6; }
  .lede span { display: block; margin-top: 10px; font-size: 22px; color: #d9c9a8; }
  .cta { position: absolute; left: 60px; bottom: 56px; padding: 14px 26px; border-radius: 999px;
         background: #f6c23e; color: #1c1412; font-family: "Bai Jamjuree"; font-weight: 600; font-size: 26px;
         box-shadow: 0 0 0 3px #1c1412, 0 0 0 5px #d4a53a, 0 8px 24px rgba(0,0,0,.45); }
  .cta b { font-weight: 600; opacity: .72; }
</style></head><body>
  <div class="map"></div><div class="shade"></div>
  <div class="plate"><div class="th">กรุงเทพมหานคร</div><div class="en">Pixel Bangkok</div></div>
  <div class="lede">An isometric pixel-art map of Bangkok, street by street.
    <span>แผนที่พิกเซลอาร์ตของกรุงเทพฯ ซูมเที่ยวได้ทุกตรอกซอกซอย</span></div>
  <div class="cta">Explore the map <b>· www.pixelbangkok.com</b></div>
</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(html, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: resolve(out), type: "jpeg", quality: 84 });
await browser.close();
console.log("wrote", resolve(out));

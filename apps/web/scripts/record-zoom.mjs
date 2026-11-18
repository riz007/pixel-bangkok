// Records a short zoom-in video of the map for sharing (launch kit).
// Usage: node scripts/record-zoom.mjs [baseUrl] [area] [placeId] [outDir]
// Needs a running app (pnpm dev or pnpm start) and `pnpm exec playwright install chromium`.
import { mkdir, rename, readdir } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

const [baseUrl = "http://localhost:3000", area = "inner-bangkok", place = "wat-arun", outDir = "../../build/launch"] =
  process.argv.slice(2);
const size = { width: 1280, height: 720 };

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: size,
  recordVideo: { dir: outDir, size },
  locale: "th-TH",
});
const page = await context.newPage();
await page.goto(`${baseUrl}/?area=${area}`);
await page.locator('.map[data-status="ready"]').waitFor({ timeout: 60_000 });
await page.waitForTimeout(2500);

const zoomIn = page.locator(".map__zoom button").first();
await page.locator(".search input").fill(place.replace(/-/g, " "));
await page.locator(".search__results button").first().click();
await page.waitForTimeout(2500);
for (let step = 0; step < 4; step += 1) {
  await zoomIn.click();
  await page.waitForTimeout(1400);
}
await page.waitForTimeout(4000);

const video = page.video();
await context.close();
await browser.close();
const recorded = video ? await video.path() : null;
if (recorded) {
  const target = path.join(outDir, `zoom-${area}-${place}.webm`);
  await rename(recorded, target);
  console.log(`saved ${target}`);
} else {
  console.log("no video recorded", await readdir(outDir));
}

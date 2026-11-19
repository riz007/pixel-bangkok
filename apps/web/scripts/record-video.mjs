// Record a launch video of the map as an H.264 MP4 (for X and other social sites).
// Frames come from Chrome's screencast, then ffmpeg encodes them at a constant 30 fps.
//
// Usage: node scripts/record-video.mjs [baseUrl] [outFile] [width] [height]
//   e.g. node scripts/record-video.mjs http://localhost:3001 ../../build/launch/pixel-bangkok.mp4
// Needs a running app, `pnpm exec playwright install chromium` and ffmpeg on PATH.
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { chromium } from "@playwright/test";

const [
  baseUrl = "http://localhost:3001",
  outFile = "../../build/launch/pixel-bangkok.mp4",
  width = "1920",
  height = "1080",
] = process.argv.slice(2);
const size = { width: Number(width), height: Number(height) };
const FPS = 30;

const frames = await mkdtemp(path.join(tmpdir(), "pixel-bangkok-frames-"));
const browser = await chromium.launch({ args: ["--force-device-scale-factor=1"] });
const context = await browser.newContext({ viewport: size, locale: "en-US", deviceScaleFactor: 1 });
const page = await context.newPage();

await page.goto(`${baseUrl}/?area=bangkok`);
await page.locator('.map[data-status="ready"]').waitFor({ timeout: 60_000 });
await page.keyboard.press("p");
// Recording only: let the wheel and drags reach the map through the place pins.
await page.addStyleTag({ content: ".map__markers, .map__markers * { pointer-events: none !important; }" });
await page.waitForTimeout(5000);

const centre = { x: size.width / 2, y: size.height / 2 };
const pause = (ms) => page.waitForTimeout(ms);

async function markerPoint(id) {
  const box = await page.locator(`[data-poi-id="${id}"]`).boundingBox();
  if (!box) throw new Error(`marker ${id} is not on screen`);
  // Just below the pin's tip: the map itself, so the pin does not swallow the wheel.
  return { x: box.x + box.width / 2, y: box.y + box.height + 6 };
}

/** Continuous zoom about a screen point: wheel steps closer together than the 0.6 s spring. */
async function zoom(point, steps, seconds) {
  await page.mouse.move(point.x, point.y);
  const interval = (seconds * 1000) / Math.abs(steps);
  for (let step = 0; step < Math.abs(steps); step += 1) {
    await page.mouse.wheel(0, steps > 0 ? -100 : 100);
    await pause(interval);
  }
}

/** Smooth drag so that `from` ends at `to`. */
async function pan(from, to, seconds) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  const moves = Math.round(seconds * FPS);
  for (let index = 1; index <= moves; index += 1) {
    const t = index / moves;
    const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    await page.mouse.move(from.x + (to.x - from.x) * eased, from.y + (to.y - from.y) * eased);
    await pause(1000 / FPS);
  }
  await page.mouse.up();
}

const client = await context.newCDPSession(page);
const shots = [];
client.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const file = path.join(frames, `${String(shots.length).padStart(6, "0")}.jpg`);
  shots.push({ file, time: metadata.timestamp });
  await writeFile(file, Buffer.from(data, "base64"));
  await client.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});
await client.send("Page.startScreencast", {
  format: "jpeg",
  quality: 92,
  maxWidth: size.width,
  maxHeight: size.height,
  everyNthFrame: 1,
});

// 1. The whole city, then glide into Rattanakosin and the Grand Palace by the river.
await pause(2500);
await zoom(await markerPoint("grand-palace"), 18, 8);
await pause(4000);
// 2. Ease back out, travel east to Ratchaprasong, and drop in on the BTS viaducts.
await zoom(centre, -7, 2.5);
await pause(600);
const erawan = await markerPoint("erawan-shrine");
await pan(erawan, centre, 2.8);
await pause(800);
await zoom(await markerPoint("erawan-shrine"), 8, 3.5);
await pause(5500);
// 3. Back out to the whole city.
await zoom(centre, -19, 5);
await pause(2500);

await client.send("Page.stopScreencast");
await pause(300);
await browser.close();

const list = shots
  .map((shot, index) => {
    const next = shots[index + 1];
    const duration = next ? Math.max(next.time - shot.time, 0.001) : 1 / FPS;
    return `file '${shot.file}'\nduration ${duration.toFixed(4)}`;
  })
  .join("\n");
const listFile = path.join(frames, "frames.txt");
await writeFile(listFile, `${list}\nfile '${shots.at(-1).file}'\n`);
await mkdir(path.dirname(path.resolve(outFile)), { recursive: true });
execFileSync(
  "ffmpeg",
  [
    "-y",
    "-loglevel",
    "error",
    "-f",
    "concat",
    "-safe",
    "0",
    "-i",
    listFile,
    "-vf",
    `fps=${FPS},scale=${size.width}:${size.height}:flags=lanczos,format=yuv420p`,
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "18",
    "-movflags",
    "+faststart",
    path.resolve(outFile),
  ],
  { stdio: "inherit" },
);
const seconds = shots.at(-1).time - shots[0].time;
console.log(`wrote ${path.resolve(outFile)}: ${shots.length} frames over ${seconds.toFixed(1)} s`);
await rm(frames, { recursive: true, force: true });

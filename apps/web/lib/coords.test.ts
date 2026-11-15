import assert from "node:assert/strict";
import { test } from "node:test";

import { imageToViewport, tileSourceOptions, tileUrl, viewportToImage } from "./coords.ts";
import { manifestFixture } from "./fixtures.ts";
import { parseManifest } from "./manifest.ts";

const manifest = parseManifest(manifestFixture());

test("image corners map to the viewport rectangle of a non-square image", () => {
  assert.deepEqual(imageToViewport({ x: 0, y: 0 }, manifest.image), { x: 0, y: 0 });
  assert.deepEqual(imageToViewport({ x: 1000, y: 300 }, manifest.image), { x: 1, y: 0.3 });
  assert.deepEqual(imageToViewport({ x: 500, y: 150 }, manifest.image), { x: 0.5, y: 0.15 });
});

test("viewport conversion round-trips", () => {
  const point = { x: 123.5, y: 287.25 };
  const back = viewportToImage(imageToViewport(point, manifest.image), manifest.image);
  assert.ok(Math.abs(back.x - point.x) < 1e-9);
  assert.ok(Math.abs(back.y - point.y) < 1e-9);
});

test("tile URLs follow the manifest template", () => {
  assert.equal(tileUrl(manifest, "/maps/test-area/", 10, 3, 1), "/maps/test-area/tiles/10/3_1.webp");
});

test("tile source options come from the manifest", () => {
  const options = tileSourceOptions(manifest, "/maps/test-area");
  assert.equal(options.width, 1000);
  assert.equal(options.height, 300);
  assert.equal(options.tileSize, 256);
  assert.equal(options.tileOverlap, 1);
  assert.equal(options.maxLevel, 10);
  assert.equal(options.getTileUrl(9, 1, 0), "/maps/test-area/tiles/9/1_0.webp");
});

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  imageToLonLat,
  imageToViewport,
  lonLatToImage,
  parseLatLon,
  tilePresence,
  tileSourceOptions,
  tileUrl,
  viewportToImage,
} from "./coords.ts";
import { GEOGRAPHIC_PROBE, manifestFixture } from "./fixtures.ts";
import { parseManifest } from "./manifest.ts";

const manifest = parseManifest(manifestFixture());

test("image corners map to the viewport rectangle of a non-square image", () => {
  assert.deepEqual(imageToViewport({ x: 0, y: 0 }, manifest.image), {
    x: 0,
    y: 0,
  });
  assert.deepEqual(imageToViewport({ x: 1000, y: 300 }, manifest.image), {
    x: 1,
    y: 0.3,
  });
  assert.deepEqual(imageToViewport({ x: 500, y: 150 }, manifest.image), {
    x: 0.5,
    y: 0.15,
  });
});

test("viewport conversion round-trips", () => {
  const point = { x: 123.5, y: 287.25 };
  const back = viewportToImage(
    imageToViewport(point, manifest.image),
    manifest.image,
  );
  assert.ok(Math.abs(back.x - point.x) < 1e-9);
  assert.ok(Math.abs(back.y - point.y) < 1e-9);
});

test("tile URLs follow the manifest template", () => {
  assert.equal(
    tileUrl(manifest, "/maps/test-area/", 10, 3, 1),
    "/maps/test-area/tiles/10/3_1.webp?v=0",
  );
  assert.equal(
    tileUrl(
      manifest,
      "/maps",
      1,
      0,
      0,
      "overlay/{level}/{column}_{row}.{format}",
      "abc",
    ),
    "/maps/overlay/1/0_0.webp?v=abc",
  );
});

test("tile source options come from the manifest", () => {
  const options = tileSourceOptions(manifest, "/maps/test-area");
  assert.equal(options.width, 1000);
  assert.equal(options.height, 300);
  assert.equal(options.tileSize, 256);
  assert.equal(options.tileOverlap, 1);
  assert.equal(options.maxLevel, 10);
  assert.equal(
    options.getTileUrl(9, 1, 0),
    "/maps/test-area/tiles/9/1_0.webp?v=0",
  );
});

test("lon/lat lands on the image pixel the pipeline projects it to", () => {
  const [lon = 0, lat = 0] = GEOGRAPHIC_PROBE.lonlat;
  const [x = 0, y = 0] = GEOGRAPHIC_PROBE.world;
  const point = lonLatToImage(manifest, lon, lat);
  assert.ok(point);
  assert.ok(Math.abs(point.x - (2.1 * x + 2.1 * y + 10)) < 0.2);
  assert.ok(Math.abs(point.y - (-0.75 * x + 0.75 * y + 200)) < 0.2);
  const back = imageToLonLat(manifest, point);
  assert.ok(back);
  assert.ok(Math.abs(back.lon - lon) < 1e-6 && Math.abs(back.lat - lat) < 1e-6);
});

test("coordinates outside the area are rejected", () => {
  assert.equal(lonLatToImage(manifest, 100.6, 13.9), null);
});

test("latitude, longitude text is parsed in map-app order", () => {
  assert.deepEqual(parseLatLon("13.7437, 100.4897"), {
    lat: 13.7437,
    lon: 100.4897,
  });
  assert.deepEqual(parseLatLon(" 13.7437 100.4897 "), {
    lat: 13.7437,
    lon: 100.4897,
  });
  assert.equal(parseLatLon("Wat Arun"), null);
  assert.equal(parseLatLon("95, 100"), null);
});

test("tiles missing from the presence bitmap are never requested", () => {
  const level = manifest.tiles.levels.find(
    (entry) => entry.columns * entry.rows >= 2,
  )!;
  const bits = new Uint8Array(Math.ceil((level.columns * level.rows) / 8));
  bits[0] = 0b01;
  const encoded = btoa(String.fromCharCode(...bits));
  const withGaps = {
    ...manifest,
    tiles: {
      ...manifest.tiles,
      present: { tiles: { [level.level]: encoded } },
    },
  };
  const exists = tilePresence(withGaps, manifest.tiles.urlTemplate);
  assert.equal(exists(level.level, 0, 0), true);
  assert.equal(
    exists(level.level, 1, 0) || level.columns === 1,
    level.columns === 1,
  );
  assert.equal(exists(level.level, level.columns, 0), false);
  assert.equal(tilePresence(manifest, "overlay/x")(level.level, 0, 0), true);
});

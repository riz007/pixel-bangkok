import assert from "node:assert/strict";
import { test } from "node:test";

import { manifestFixture, poisFixture } from "./fixtures.ts";
import { DataError, parseAreaIndex, parseManifest, parsePois } from "./manifest.ts";

test("parses a valid manifest", () => {
  const manifest = parseManifest(manifestFixture());
  assert.equal(manifest.areaId, "test-area");
  assert.deepEqual(manifest.image, { width: 1000, height: 300 });
  assert.equal(manifest.tiles.tileSize, 256);
  assert.equal(manifest.tiles.overlap, 1);
  assert.equal(manifest.tiles.maxLevel, 10);
  assert.equal(manifest.tiles.levels.length, 2);
  assert.equal(manifest.attributions.length, 2);
  assert.equal(manifest.attributions[0]?.text, "© OpenStreetMap contributors");
  assert.equal(manifest.attributions[1]?.licence, "CC BY 4.0");
  assert.equal(manifest.source.retrievedAt, "2026-01-01T00:00:00+00:00");
});

test("rejects malformed manifests with a descriptive error", () => {
  const base = manifestFixture();
  const cases: [string, unknown, RegExp][] = [
    ["not an object", [], /must be an object/],
    ["unsupported version", { ...base, version: 3 }, /unsupported manifest version/],
    ["missing image", { ...base, image: undefined }, /manifest\.image must be an object/],
    [
      "zero tile size",
      { ...base, tiles: { ...base.tiles, tile_size: 0 } },
      /tile_size must be a positive integer/,
    ],
    [
      "string width",
      { ...base, image: { ...base.image, width: "1000" } },
      /width must be a finite number/,
    ],
    [
      "level mismatch",
      { ...base, image: { ...base.image, width: 999 } },
      /top level does not match/,
    ],
    ["missing attributions", { ...base, attributions: undefined }, /attributions must be an array/],
    ["empty attributions", { ...base, attributions: [] }, /attributions must not be empty/],
    [
      "attribution without url",
      { ...base, attributions: [{ text: "x", licence: "y", provider: "z" }] },
      /attributions\[0\]\.url must be a non-empty string/,
    ],
    ["version 1 manifest", { ...base, version: 1 }, /unsupported manifest version 1/],
  ];
  for (const [name, input, pattern] of cases) {
    assert.throws(
      () => parseManifest(input),
      (error) => error instanceof DataError && pattern.test(error.message),
      name,
    );
  }
});

test("parses POIs with independent Thai and English names", () => {
  const pois = parsePois(poisFixture(), parseManifest(manifestFixture()));
  assert.equal(pois.length, 2);
  assert.equal(pois[0]?.nameEn, "Wat Arun Central Prang");
  assert.equal(pois[0]?.nameTh, "พระปรางค์วัดอรุณ");
  assert.deepEqual(pois[0]?.image, { x: 500, y: 150 });
  assert.equal(pois[1]?.sourceUrl, null);
});

test("rejects POIs outside the image and duplicate ids", () => {
  const manifest = parseManifest(manifestFixture());
  const [first, second] = poisFixture().pois;
  const outside = { pois: [{ ...first, image: { x: 1001, y: 150 } }, second] };
  assert.throws(() => parsePois(outside, manifest), /outside the map image/);
  const duplicate = { pois: [first, { ...second, id: "prang" }] };
  assert.throws(() => parsePois(duplicate, manifest), /duplicate POI id/);
});

test("parses the area index", () => {
  const areas = parseAreaIndex({ areas: [{ id: "wat-arun", name: { en: "Wat Arun", th: null } }] });
  assert.deepEqual(areas, [{ id: "wat-arun", name: { en: "Wat Arun", th: null } }]);
  assert.throws(() => parseAreaIndex({ areas: [{ id: "" }] }), DataError);
});

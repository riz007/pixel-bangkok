import assert from "node:assert/strict";
import { test } from "node:test";

import { manifestFixture, poisFixture } from "./fixtures.ts";
import { lineLabel } from "./i18n.ts";
import {
  DataError,
  parseAreaIndex,
  parseManifest,
  parsePois,
} from "./manifest.ts";

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
  assert.deepEqual(manifest.projection.worldToImage.px, [2.1, 2.1, 0, 10]);
  assert.equal(manifest.projection.cameraAzimuthDeg, 315);
  assert.equal(manifest.animation?.motionUrl, "motion.json");
  const withoutAnimation: Record<string, unknown> = { ...manifestFixture() };
  delete withoutAnimation.animation;
  assert.equal(parseManifest(withoutAnimation).animation, null);
  assert.equal(manifest.ai, null);
  const withAi = parseManifest({
    ...manifestFixture(),
    ai: {
      url_template: "ai/{level}/{column}_{row}.{format}",
      overlay_url_template: null,
      model: "Test model",
      licence: "Apache 2.0",
      coverage: 0.25,
    },
  });
  assert.equal(withAi.ai?.coverage, 0.25);
  assert.throws(
    () => parseManifest({ ...manifestFixture(), ai: { model: "x" } }),
    /manifest\.ai\.url_template/,
  );
  assert.equal(manifest.source.retrievedAt, "2026-01-01T00:00:00+00:00");
});

test("rejects malformed manifests with a descriptive error", () => {
  const base = manifestFixture();
  const cases: [string, unknown, RegExp][] = [
    ["not an object", [], /must be an object/],
    [
      "unsupported version",
      { ...base, version: 4 },
      /unsupported manifest version/,
    ],
    [
      "missing image",
      { ...base, image: undefined },
      /manifest\.image must be an object/,
    ],
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
    [
      "missing attributions",
      { ...base, attributions: undefined },
      /attributions must be an array/,
    ],
    [
      "empty attributions",
      { ...base, attributions: [] },
      /attributions must not be empty/,
    ],
    [
      "attribution without url",
      { ...base, attributions: [{ text: "x", licence: "y", provider: "z" }] },
      /attributions\[0\]\.url must be a non-empty string/,
    ],
    [
      "version 2 manifest",
      { ...base, version: 2 },
      /unsupported manifest version 2/,
    ],
    [
      "short matrix",
      {
        ...base,
        projection: {
          ...base.projection,
          world_to_image: { px: [1, 2], py: [1, 2, 3, 4] },
        },
      },
      /world_to_image\.px must be four numbers/,
    ],
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

test("parses a station's line and rejects a malformed one", () => {
  const manifest = parseManifest(manifestFixture());
  const [first, second] = poisFixture().pois;
  const line = {
    en: "BTS Silom Line",
    th: "รถไฟฟ้าบีทีเอส สายสีลม",
    code: "S2",
  };
  const pois = parsePois({ pois: [{ ...first, line }, second] }, manifest);
  assert.deepEqual(pois[0]?.line, line);
  assert.equal(pois[1]?.line, null);
  assert.equal(lineLabel(line, "en"), "BTS Silom Line · S2");
  assert.equal(
    lineLabel({ ...line, code: "" }, "th"),
    "รถไฟฟ้าบีทีเอส สายสีลม",
  );
  const broken = { pois: [{ ...first, line: { en: "BTS" } }, second] };
  assert.throws(() => parsePois(broken, manifest), /line\.th/);
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
  const areas = parseAreaIndex({
    areas: [{ id: "wat-arun", name: { en: "Wat Arun", th: null } }],
  });
  assert.deepEqual(areas, [
    { id: "wat-arun", name: { en: "Wat Arun", th: null } },
  ]);
  assert.throws(() => parseAreaIndex({ areas: [{ id: "" }] }), DataError);
});

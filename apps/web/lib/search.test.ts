import assert from "node:assert/strict";
import { test } from "node:test";

import { manifestFixture, poisFixture } from "./fixtures.ts";
import { parseManifest, parsePois } from "./manifest.ts";
import { normaliseQuery, searchPois } from "./search.ts";

const pois = parsePois(poisFixture(), parseManifest(manifestFixture()));
const ids = (query: string) => searchPois(pois, query).map((poi) => poi.id);

test("matches English names case-insensitively", () => {
  assert.deepEqual(ids("wat arun"), ["prang"]);
  assert.deepEqual(ids("  THA  tien "), ["pier"]);
});

test("matches Thai names and aliases", () => {
  assert.deepEqual(ids("ท่าเตียน"), ["pier"]);
  assert.deepEqual(ids("วัดแจ้ง"), ["prang"]);
  assert.deepEqual(ids("temple of dawn"), ["prang"]);
});

test("matches a category and ranks prefix matches first", () => {
  assert.deepEqual(ids("pier"), ["pier"]);
  assert.deepEqual(ids("t"), ["pier", "prang"]);
});

test("returns nothing for empty or unmatched queries", () => {
  assert.deepEqual(ids("   "), []);
  assert.deepEqual(ids("airport"), []);
});

test("normalises diacritics and whitespace", () => {
  assert.equal(normaliseQuery("  Café   Été "), "cafe ete");
});

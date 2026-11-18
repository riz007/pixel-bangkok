import assert from "node:assert/strict";
import { test } from "node:test";

import type { PointOfInterest } from "./manifest.ts";
import { markerBudget, visibleMarkerIds } from "./visibility.ts";

function poi(id: string, rank: number | null): PointOfInterest {
  return {
    id,
    nameEn: id,
    nameTh: null,
    aliases: [],
    category: "temple",
    lon: 0,
    lat: 0,
    description: "",
    source: null,
    sourceUrl: null,
    rank,
    thumbnail: null,
    image: { x: 0, y: 0 },
  };
}

test("budget grows as you zoom in", () => {
  assert.equal(markerBudget(0.05, 150), 15);
  assert.equal(markerBudget(0.15, 150), 30);
  assert.equal(markerBudget(0.25, 150), 60);
  assert.equal(markerBudget(0.5, 150), 150);
  assert.equal(markerBudget(0.05, 4), 4);
});

test("most notable landmarks win, curated first, selection always shown", () => {
  const pois = [poi("minor", 2), ...Array.from({ length: 20 }, (_, i) => poi(`p${i}`, 100 - i)), poi("curated", null)];
  const far = visibleMarkerIds(pois, 0.05, null);
  assert.equal(far.size, 15);
  assert.ok(far.has("curated"));
  assert.ok(far.has("p0"));
  assert.ok(!far.has("minor"));
  assert.ok(visibleMarkerIds(pois, 0.05, "minor").has("minor"));
  assert.equal(visibleMarkerIds(pois, 1, null).size, pois.length);
});

import assert from "node:assert/strict";
import { test } from "node:test";

import { detectLang, placeName } from "./i18n.ts";
import type { PointOfInterest } from "./manifest.ts";
import { tourOrder } from "./tour.ts";

function poi(id: string, x: number, y: number, lat: number, rank: number | null): PointOfInterest {
  return {
    id,
    nameEn: id,
    nameTh: null,
    aliases: [],
    category: "temple",
    lon: 0,
    lat,
    description: "",
    source: null,
    sourceUrl: null,
    rank,
    thumbnail: null,
    line: null,
    image: { x, y },
  };
}

test("tour starts north and walks to the nearest next stop", () => {
  const pois = [
    poi("south", 0, 100, 13.70, 50),
    poi("north", 0, 0, 13.80, 40),
    poi("middle", 0, 50, 13.75, 30),
    poi("east", 500, 0, 13.79, 20),
  ];
  assert.deepEqual(tourOrder(pois).map((p) => p.id), ["north", "middle", "south", "east"]);
});

test("tour keeps the most notable places, curated first", () => {
  const pois = [poi("minor", 0, 0, 13.7, 1), poi("major", 10, 0, 13.71, 99), poi("curated", 20, 0, 13.72, null)];
  assert.deepEqual(tourOrder(pois, 2).map((p) => p.id).sort(), ["curated", "major"]);
  assert.deepEqual(tourOrder([]), []);
});

test("language detection and bilingual names", () => {
  assert.equal(detectLang(["th-TH", "en"]), "th");
  assert.equal(detectLang(["en-GB"]), "en");
  const wat = { nameEn: "Wat Arun", nameTh: "วัดอรุณ" };
  assert.deepEqual(placeName(wat, "th"), { primary: "วัดอรุณ", secondary: "Wat Arun" });
  assert.deepEqual(placeName(wat, "en"), { primary: "Wat Arun", secondary: "วัดอรุณ" });
  assert.deepEqual(placeName({ nameEn: "Siam", nameTh: null }, "th"), { primary: "Siam", secondary: null });
});

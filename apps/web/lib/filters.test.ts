import assert from "node:assert/strict";
import { test } from "node:test";

import { filterCounts, filterPlaces, findFilter } from "./filters.ts";

const places = [
  { id: "wat-arun", category: "temple" },
  { id: "siam", category: "transit" },
  { id: "tha-tien", category: "pier" },
  { id: "lumphini", category: "park" },
];

test("a filter keeps its categories and grouped ones", () => {
  const transit = findFilter("transit");
  assert.deepEqual(
    filterPlaces(places, transit).map((place) => place.id),
    ["siam", "tha-tien"],
  );
  assert.equal(filterPlaces(places, null).length, 4);
  assert.equal(findFilter("nope"), null);
});

test("the selected place stays visible under any filter", () => {
  const ids = filterPlaces(places, findFilter("parks"), "wat-arun").map(
    (place) => place.id,
  );
  assert.deepEqual(ids, ["wat-arun", "lumphini"]);
});

test("counts list only filters that have places", () => {
  const counts = Object.fromEntries(
    filterCounts(places).map((e) => [e.filter.id, e.count]),
  );
  assert.deepEqual(counts, { worship: 1, transit: 2, parks: 1 });
});

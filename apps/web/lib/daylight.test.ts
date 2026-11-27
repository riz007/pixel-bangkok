import assert from "node:assert/strict";
import { test } from "node:test";

import { bangkokClock, skyAt, skyFor, sunTimes } from "./daylight.ts";

/** A moment given in Bangkok wall-clock time (UTC+7). */
function bangkok(iso: string): Date {
  return new Date(`${iso}+07:00`);
}

function within(actual: Date, expected: Date, minutes: number) {
  const off = Math.abs(actual.getTime() - expected.getTime()) / 60_000;
  assert.ok(
    off <= minutes,
    `${actual.toISOString()} is ${off.toFixed(1)} min off`,
  );
}

test("Bangkok sunrise and sunset match published times within a few minutes", () => {
  // Published times for Bangkok: about 05:51 and 18:46 on 21 June, 06:39 and 17:56 on
  // 21 December.
  const june = sunTimes(bangkok("2026-06-21T12:00:00"));
  within(june.sunrise, bangkok("2026-06-21T05:51:00"), 6);
  within(june.sunset, bangkok("2026-06-21T18:46:00"), 6);
  const december = sunTimes(bangkok("2026-12-21T12:00:00"));
  within(december.sunrise, bangkok("2026-12-21T06:39:00"), 6);
  within(december.sunset, bangkok("2026-12-21T17:56:00"), 6);
});

test("the sky is light at noon, dark at night and in between at dusk and dawn", () => {
  assert.deepEqual(skyAt(bangkok("2026-11-27T12:00:00")), {
    phase: "day",
    darkness: 0,
  });
  assert.deepEqual(skyAt(bangkok("2026-11-27T22:00:00")), {
    phase: "night",
    darkness: 1,
  });
  assert.deepEqual(skyAt(bangkok("2026-11-27T02:00:00")), {
    phase: "night",
    darkness: 1,
  });
  const { sunset, sunrise } = sunTimes(bangkok("2026-11-27T12:00:00"));
  const dusk = skyAt(sunset);
  assert.equal(dusk.phase, "dusk");
  assert.ok(dusk.darkness > 0.2 && dusk.darkness < 0.8);
  const dawn = skyAt(sunrise);
  assert.equal(dawn.phase, "dawn");
  assert.ok(dawn.darkness > 0.2 && dawn.darkness < 0.8);
});

test("dusk darkens steadily and dawn brightens steadily", () => {
  const { sunset, sunrise } = sunTimes(bangkok("2026-11-27T12:00:00"));
  const at = (base: Date, minutes: number) =>
    skyAt(new Date(base.getTime() + minutes * 60_000)).darkness;
  assert.ok(at(sunset, -20) < at(sunset, 0) && at(sunset, 0) < at(sunset, 30));
  assert.ok(
    at(sunrise, -30) > at(sunrise, 0) && at(sunrise, 0) > at(sunrise, 20),
  );
});

test("a chosen mode overrides the clock, and the clock shows Bangkok time", () => {
  const noon = bangkok("2026-11-27T12:00:00");
  assert.equal(skyFor("night", noon).phase, "night");
  assert.equal(skyFor("day", bangkok("2026-11-27T23:00:00")).darkness, 0);
  assert.equal(skyFor("auto", noon).phase, "day");
  assert.equal(bangkokClock(bangkok("2026-11-27T21:05:00")), "21:05");
});

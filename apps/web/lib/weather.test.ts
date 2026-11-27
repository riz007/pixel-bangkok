import assert from "node:assert/strict";
import { test } from "node:test";

import {
  aqiBandFor,
  cloudFor,
  conditionFor,
  hazeFor,
  parseWeather,
} from "./weather.ts";

const forecast = {
  current: {
    time: "2026-11-27T19:15",
    temperature_2m: 30.8,
    weather_code: 63,
    precipitation: 1.2,
    cloud_cover: 91,
    wind_speed_10m: 3.7,
  },
};
const air = {
  current: { time: "2026-11-27T19:00", pm2_5: 52.4, us_aqi_pm2_5: 142 },
};

test("Open-Meteo responses become the weather the map draws", () => {
  assert.deepEqual(parseWeather(forecast, air), {
    observedAt: "2026-11-27T19:15",
    temperatureC: 30.8,
    condition: "rain",
    precipitationMm: 1.2,
    cloudCover: 91,
    windKmh: 3.7,
    pm25: 52.4,
    aqi: 142,
    aqiBand: "sensitive",
  });
});

test("weather without air quality still works, and broken weather throws", () => {
  const weather = parseWeather(forecast, null);
  assert.equal(weather.pm25, null);
  assert.equal(weather.aqiBand, null);
  assert.throws(() => parseWeather({ current: {} }, air));
  assert.throws(() => parseWeather(null, air));
});

test("WMO codes map to the conditions the map can draw", () => {
  assert.equal(conditionFor(0, 0), "clear");
  assert.equal(conditionFor(2, 0), "partly");
  assert.equal(conditionFor(3, 0), "cloudy");
  assert.equal(conditionFor(45, 0), "fog");
  assert.equal(conditionFor(53, 0.2), "drizzle");
  assert.equal(conditionFor(81, 4), "rain");
  assert.equal(conditionFor(95, 10), "storm");
});

test("AQI bands follow the US EPA categories", () => {
  assert.deepEqual([42, 72, 120, 180, 250, 320].map(aqiBandFor), [
    "good",
    "moderate",
    "sensitive",
    "unhealthy",
    "very-unhealthy",
    "hazardous",
  ]);
});

test("haze grows with PM2.5 and never hides the map", () => {
  assert.equal(hazeFor(null), 0);
  assert.equal(hazeFor(10), 0);
  assert.ok(hazeFor(40) > 0 && hazeFor(40) < hazeFor(90));
  assert.ok(hazeFor(500) <= 0.32);
  const storm = parseWeather(
    { current: { ...forecast.current, weather_code: 95 } },
    air,
  );
  assert.ok(cloudFor(storm) > cloudFor(parseWeather(forecast, air)));
});

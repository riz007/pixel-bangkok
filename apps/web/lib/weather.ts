/** Live Bangkok weather and air quality from Open-Meteo, reduced to what the map draws.
 *
 * Weather is Open-Meteo's forecast model at its "current" 15-minute step; air quality is the
 * CAMS global model (about 45 km cells), so both are modelled values for central Bangkok, not
 * station readings. The map shows PM2.5 with its own US AQI sub-index, because the overall
 * US AQI takes the worst pollutant (often ozone) and would not match the haze being drawn.
 */

export const WEATHER_POINT = { lat: 13.7563, lon: 100.5018 } as const;

export const FORECAST_URL =
  "https://api.open-meteo.com/v1/forecast" +
  `?latitude=${WEATHER_POINT.lat}&longitude=${WEATHER_POINT.lon}` +
  "&current=temperature_2m,weather_code,precipitation,cloud_cover,wind_speed_10m" +
  "&timezone=Asia%2FBangkok";

export const AIR_QUALITY_URL =
  "https://air-quality-api.open-meteo.com/v1/air-quality" +
  `?latitude=${WEATHER_POINT.lat}&longitude=${WEATHER_POINT.lon}` +
  "&current=pm2_5,us_aqi_pm2_5&timezone=Asia%2FBangkok";

export const WEATHER_CREDIT = {
  text: "Weather and air quality: Open-Meteo.com and Copernicus (CAMS)",
  url: "https://open-meteo.com/",
  licence: "CC BY 4.0",
} as const;

export type Condition =
  | "clear"
  | "partly"
  | "cloudy"
  | "fog"
  | "drizzle"
  | "rain"
  | "storm";

export type AqiBand =
  | "good"
  | "moderate"
  | "sensitive"
  | "unhealthy"
  | "very-unhealthy"
  | "hazardous";

export interface Weather {
  /** Bangkok local time of the model step, "YYYY-MM-DDTHH:MM". */
  observedAt: string;
  temperatureC: number;
  condition: Condition;
  precipitationMm: number;
  cloudCover: number;
  windKmh: number;
  pm25: number | null;
  aqi: number | null;
  aqiBand: AqiBand | null;
}

/** WMO weather interpretation codes, as Open-Meteo returns them. */
export function conditionFor(code: number, precipitationMm: number): Condition {
  if (code >= 95) return "storm";
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return "rain";
  if (code >= 51 && code <= 57) return "drizzle";
  if (code === 45 || code === 48) return "fog";
  if (code === 3) return precipitationMm > 0 ? "drizzle" : "cloudy";
  if (code === 1 || code === 2) return "partly";
  if (code === 0) return "clear";
  // Snow and other codes do not occur in Bangkok; draw them as cloud.
  return "cloudy";
}

/** US EPA AQI categories. */
export function aqiBandFor(aqi: number): AqiBand {
  if (aqi <= 50) return "good";
  if (aqi <= 100) return "moderate";
  if (aqi <= 150) return "sensitive";
  if (aqi <= 200) return "unhealthy";
  if (aqi <= 300) return "very-unhealthy";
  return "hazardous";
}

/** How strongly to haze the map: none in clean air, rising with PM2.5, capped so the map
 * always stays readable. */
export function hazeFor(pm25: number | null): number {
  if (pm25 === null || pm25 <= 15) return 0;
  return Math.min(0.32, ((pm25 - 15) / 135) * 0.32);
}

/** How strongly to grey the map for cloud. */
export function cloudFor(weather: Weather): number {
  const base = (weather.cloudCover / 100) * 0.12;
  if (weather.condition === "storm") return 0.3;
  if (weather.condition === "rain") return Math.max(base, 0.2);
  if (weather.condition === "drizzle" || weather.condition === "fog")
    return Math.max(base, 0.14);
  return base;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Combine the two Open-Meteo responses; throws when the weather part is unusable. Air quality
 * is optional: without it the map still shows the weather. */
export function parseWeather(forecast: unknown, air: unknown): Weather {
  const current = (forecast as { current?: Record<string, unknown> })?.current;
  const temperature = finite(current?.temperature_2m);
  const code = finite(current?.weather_code);
  if (!current || temperature === null || code === null) {
    throw new Error("Open-Meteo forecast has no current weather");
  }
  const precipitation = finite(current.precipitation) ?? 0;
  const airCurrent = (air as { current?: Record<string, unknown> } | null)
    ?.current;
  const pm25 = finite(airCurrent?.pm2_5);
  const aqi = finite(airCurrent?.us_aqi_pm2_5);
  return {
    observedAt: String(current.time ?? ""),
    temperatureC: temperature,
    condition: conditionFor(code, precipitation),
    precipitationMm: precipitation,
    cloudCover: finite(current.cloud_cover) ?? 0,
    windKmh: finite(current.wind_speed_10m) ?? 0,
    pm25,
    aqi,
    aqiBand: aqi === null ? null : aqiBandFor(aqi),
  };
}

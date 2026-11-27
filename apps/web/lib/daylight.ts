/** Day and night over Bangkok: sunrise and sunset from the sun's position, and how dark the
 * sky is at a given moment.
 *
 * Sun times use the NOAA approximation (declination and equation of time from the day of the
 * year), accurate to a few minutes, which is plenty for tinting a map. Everything is computed in
 * UTC and shown in Bangkok time (UTC+7, no daylight saving).
 */

export const BANGKOK = { lat: 13.7563, lon: 100.5018 } as const;
export const BANGKOK_OFFSET_MINUTES = 7 * 60;

/** Civil twilight lasts about 22 minutes at Bangkok's latitude; the tint fades over a little
 * more so dusk reads as dusk. */
const TWILIGHT_BEFORE_MINUTES = 25;
const TWILIGHT_AFTER_MINUTES = 35;

export type SkyPhase = "day" | "dusk" | "night" | "dawn";
export type LightMode = "auto" | "day" | "night";
export const LIGHT_MODES: LightMode[] = ["auto", "day", "night"];

export interface Sky {
  phase: SkyPhase;
  /** 0 in full daylight, 1 at night. */
  darkness: number;
}

const DEG = Math.PI / 180;

function dayOfYear(date: Date): number {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0);
  return Math.floor((date.getTime() - start) / 86_400_000);
}

/** Sunrise and sunset for the UTC calendar day of `date`, as timestamps. */
export function sunTimes(
  date: Date,
  lat: number = BANGKOK.lat,
  lon: number = BANGKOK.lon,
): { sunrise: Date; sunset: Date } {
  const n = dayOfYear(date);
  const declination = -23.44 * Math.cos(((2 * Math.PI) / 365) * (n + 10));
  const b = ((2 * Math.PI) / 365) * (n - 81);
  const equationOfTime =
    9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b);
  // The sun's centre 0.833° below the horizon: refraction plus the radius of the disc.
  const cosHourAngle =
    (Math.sin(-0.833 * DEG) -
      Math.sin(lat * DEG) * Math.sin(declination * DEG)) /
    (Math.cos(lat * DEG) * Math.cos(declination * DEG));
  const hourAngle = Math.acos(Math.min(1, Math.max(-1, cosHourAngle))) / DEG;
  const noonMinutes = 720 - 4 * lon - equationOfTime;
  const midnight = Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate(),
  );
  return {
    sunrise: new Date(midnight + (noonMinutes - 4 * hourAngle) * 60_000),
    sunset: new Date(midnight + (noonMinutes + 4 * hourAngle) * 60_000),
  };
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** How dark the Bangkok sky is at `now`. */
export function skyAt(now: Date): Sky {
  // Sun times for the Bangkok calendar day. Bangkok's sunrise comes out as a negative offset
  // from that day's UTC midnight, which is the previous UTC evening, as it should be.
  const local = new Date(now.getTime() + BANGKOK_OFFSET_MINUTES * 60_000);
  const { sunrise, sunset } = sunTimes(
    new Date(
      Date.UTC(
        local.getUTCFullYear(),
        local.getUTCMonth(),
        local.getUTCDate(),
        12,
      ),
    ),
  );
  const rise = sunrise.getTime();
  const minutes = (time: number) => (now.getTime() - time) / 60_000;
  const sinceRise = minutes(rise);
  const sinceSet = minutes(sunset.getTime());
  if (
    sinceRise >= -TWILIGHT_AFTER_MINUTES &&
    sinceRise < TWILIGHT_BEFORE_MINUTES
  ) {
    const darkness = clamp01(
      (TWILIGHT_BEFORE_MINUTES - sinceRise) /
        (TWILIGHT_BEFORE_MINUTES + TWILIGHT_AFTER_MINUTES),
    );
    return { phase: "dawn", darkness };
  }
  if (
    sinceSet >= -TWILIGHT_BEFORE_MINUTES &&
    sinceSet < TWILIGHT_AFTER_MINUTES
  ) {
    const darkness = clamp01(
      (sinceSet + TWILIGHT_BEFORE_MINUTES) /
        (TWILIGHT_BEFORE_MINUTES + TWILIGHT_AFTER_MINUTES),
    );
    return { phase: "dusk", darkness };
  }
  if (
    sinceRise >= TWILIGHT_BEFORE_MINUTES &&
    sinceSet < -TWILIGHT_BEFORE_MINUTES
  ) {
    return { phase: "day", darkness: 0 };
  }
  return { phase: "night", darkness: 1 };
}

/** The sky to draw for a chosen light mode. */
export function skyFor(mode: LightMode, now: Date): Sky {
  if (mode === "day") return { phase: "day", darkness: 0 };
  if (mode === "night") return { phase: "night", darkness: 1 };
  return skyAt(now);
}

/** Bangkok wall-clock time, "HH:MM". */
export function bangkokClock(now: Date): string {
  const local = new Date(now.getTime() + BANGKOK_OFFSET_MINUTES * 60_000);
  const hours = String(local.getUTCHours()).padStart(2, "0");
  const minutes = String(local.getUTCMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

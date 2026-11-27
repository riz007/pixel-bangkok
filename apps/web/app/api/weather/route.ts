import { NextResponse } from "next/server";

import { AIR_QUALITY_URL, FORECAST_URL, parseWeather } from "@/lib/weather";

/** Bangkok weather for the map, fetched on the server and cached for ten minutes, so the
 * free Open-Meteo API sees a few hundred calls a day however many people visit, and
 * visitors' addresses are never sent to a third party. */
const CACHE_SECONDS = 600;

async function getJson(url: string): Promise<unknown> {
  const response = await fetch(url, {
    next: { revalidate: CACHE_SECONDS },
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  return response.json();
}

export async function GET() {
  try {
    const [forecast, air] = await Promise.all([
      getJson(FORECAST_URL),
      getJson(AIR_QUALITY_URL).catch(() => null),
    ]);
    return NextResponse.json(parseWeather(forecast, air), {
      headers: {
        "Cache-Control": `public, s-maxage=${CACHE_SECONDS}, stale-while-revalidate=${CACHE_SECONDS * 2}`,
      },
    });
  } catch {
    return NextResponse.json(
      { error: "weather unavailable" },
      { status: 503, headers: { "Cache-Control": "public, s-maxage=60" } },
    );
  }
}

import type { Metadata } from "next";

import { MapExplorer } from "@/features/map/MapExplorer";
import { areas, canonicalArea, placeCard, places } from "@/lib/server-data";
import {
  clip,
  DESCRIPTION,
  OG_IMAGE_PATH,
  SHORT_DESCRIPTION,
  SITE_NAME,
} from "@/lib/site";

const OG_IMAGE = { url: OG_IMAGE_PATH, width: 1200, height: 630 };
const TITLE_LIMIT = 60 - ` · ${SITE_NAME}`.length;

interface HomePageProps {
  searchParams: Promise<{
    area?: string | string[];
    place?: string | string[];
    filter?: string | string[];
  }>;
}

function single(value: string | string[] | undefined): string | null {
  return typeof value === "string" ? value : null;
}

export async function generateMetadata({
  searchParams,
}: HomePageProps): Promise<Metadata> {
  const params = await searchParams;
  const areaId = single(params.area);
  const placeId = single(params.place);
  if (!areaId && !placeId) return {};
  const published = await areas();
  const area = published.find((entry) => entry.id === areaId) ?? published[0];
  if (!area) return {};
  const place = placeId
    ? (await places(area.id)).find((entry) => entry.id === placeId)
    : null;
  // A place shown in several areas has one canonical address, so Google indexes it once.
  const canonicalAreaId = place
    ? ((await canonicalArea(place.id)) ?? area.id)
    : area.id;
  const query = new URLSearchParams({
    area: canonicalAreaId,
    ...(place ? { place: place.id } : {}),
  });
  const canonical = `/?${query.toString()}`;
  if (place) {
    const bilingual = place.name_th
      ? `${place.name_en} · ${place.name_th}`
      : place.name_en;
    const title = clip(
      bilingual.length <= TITLE_LIMIT ? bilingual : place.name_en,
      TITLE_LIMIT,
    );
    const lead = place.description
      ? `${place.description.charAt(0).toUpperCase()}${place.description.slice(1)}. `
      : "";
    const summary = `${lead}See ${place.name_en} on ${SITE_NAME}, a pixel-art map of Bangkok.`;
    const description = clip(summary, 155);
    const social = clip(summary, 125);
    return {
      title: { absolute: `${title} · ${SITE_NAME}` },
      description,
      alternates: { canonical },
      openGraph: {
        title,
        description: social,
        url: canonical,
        images: [OG_IMAGE],
      },
      twitter: {
        card: "summary_large_image",
        title,
        description: social,
        images: [OG_IMAGE.url],
      },
    };
  }
  const bilingual = area.name.th
    ? `${area.name.en} · ${area.name.th}`
    : area.name.en;
  const title = clip(
    bilingual.length <= TITLE_LIMIT ? bilingual : area.name.en,
    TITLE_LIMIT,
  );
  return {
    title: { absolute: `${title} · ${SITE_NAME}` },
    description: DESCRIPTION,
    alternates: { canonical },
    openGraph: {
      title,
      description: SHORT_DESCRIPTION,
      url: canonical,
      images: [OG_IMAGE],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: SHORT_DESCRIPTION,
      images: [OG_IMAGE.url],
    },
  };
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const { area, place, filter } = await searchParams;
  const areaId = single(area);
  const placeId = single(place);
  const firstArea = areaId ?? (await areas())[0]?.id ?? null;
  const initialPlace =
    firstArea && placeId ? await placeCard(firstArea, placeId) : null;
  return (
    <MapExplorer
      initialAreaId={areaId}
      initialPlaceId={placeId}
      initialFilter={single(filter)}
      initialPlace={initialPlace}
    />
  );
}

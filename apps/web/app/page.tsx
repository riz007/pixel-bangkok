import type { Metadata } from "next";

import { MapExplorer } from "@/features/map/MapExplorer";
import { areas, places } from "@/lib/server-data";
import { SITE_NAME } from "@/lib/site";

const OG_IMAGE = { url: "/og.png", width: 1200, height: 630 };

interface HomePageProps {
  searchParams: Promise<{ area?: string | string[]; place?: string | string[] }>;
}

function single(value: string | string[] | undefined): string | null {
  return typeof value === "string" ? value : null;
}

export async function generateMetadata({ searchParams }: HomePageProps): Promise<Metadata> {
  const params = await searchParams;
  const areaId = single(params.area);
  const placeId = single(params.place);
  if (!areaId && !placeId) return {};
  const published = await areas();
  const area = published.find((entry) => entry.id === areaId) ?? published[0];
  if (!area) return {};
  const query = new URLSearchParams({ area: area.id, ...(placeId ? { place: placeId } : {}) });
  const canonical = `/?${query.toString()}`;
  const place = placeId ? (await places(area.id)).find((entry) => entry.id === placeId) : null;
  if (place) {
    const title = place.name_th ? `${place.name_en} · ${place.name_th}` : place.name_en;
    const description = `${place.description} See ${place.name_en} on ${SITE_NAME}, an isometric pixel-art map of Bangkok.`;
    return {
      title,
      description,
      alternates: { canonical },
      openGraph: { title, description, url: canonical, images: [OG_IMAGE] },
      twitter: { card: "summary_large_image", title, description, images: [OG_IMAGE.url] },
    };
  }
  const title = area.name.th ? `${area.name.en} · ${area.name.th}` : area.name.en;
  return {
    title,
    alternates: { canonical },
    openGraph: { title, url: canonical, images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title, images: [OG_IMAGE.url] },
  };
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const { area, place } = await searchParams;
  return <MapExplorer initialAreaId={single(area)} initialPlaceId={single(place)} />;
}

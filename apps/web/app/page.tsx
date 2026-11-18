import { MapExplorer } from "@/features/map/MapExplorer";

interface HomePageProps {
  searchParams: Promise<{ area?: string | string[]; place?: string | string[] }>;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const { area, place } = await searchParams;
  return (
    <MapExplorer
      initialAreaId={typeof area === "string" ? area : null}
      initialPlaceId={typeof place === "string" ? place : null}
    />
  );
}

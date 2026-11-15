import { MapExplorer } from "@/features/map/MapExplorer";

interface HomePageProps {
  searchParams: Promise<{ area?: string | string[] }>;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const { area } = await searchParams;
  return <MapExplorer initialAreaId={typeof area === "string" ? area : null} />;
}

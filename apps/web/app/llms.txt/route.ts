import { FULL_NAME_ROMAN, FULL_NAME_TH, STRINGS } from "@/lib/i18n";
import { areas, places } from "@/lib/server-data";
import {
  absolute,
  DESCRIPTION,
  REPO_URL,
  SITE_NAME,
  SITE_NAME_TH,
} from "@/lib/site";

export const revalidate = 3600;

const FEATURED = 12;

export async function GET(): Promise<Response> {
  const lines = [
    `# ${SITE_NAME} (${SITE_NAME_TH})`,
    "",
    `> ${DESCRIPTION}`,
    "",
    "Pixel Bangkok is a free, interactive isometric pixel-art map of Bangkok (Krung Thep Maha Nakhon, Thailand) in Thai and English. Every building, road, canal, railway and tree is placed from OpenStreetMap with one fixed isometric projection, so positions and distances are real. Building heights come from Google Open Buildings 2.5D Temporal or OpenStreetMap; tree symbols follow the Meta and WRI canopy height map; landmark descriptions come from Wikidata. No AI image model is used: nothing on the map is invented.",
    "",
    `Bangkok's ceremonial name: ${FULL_NAME_TH} (${FULL_NAME_ROMAN}).`,
    "",
    "## Maps",
    "",
  ];
  for (const area of await areas()) {
    const name = area.name.th
      ? `${area.name.en} (${area.name.th})`
      : area.name.en;
    lines.push(`- [${name}](${absolute(`/?area=${area.id}`)})`);
  }
  const [main] = await areas();
  if (main) {
    const featured = (await places(main.id))
      .filter((place) => place.rank !== null && place.description)
      .sort((a, b) => (b.rank ?? 0) - (a.rank ?? 0))
      .slice(0, FEATURED);
    if (featured.length > 0) {
      lines.push("", "## Places", "");
      for (const place of featured) {
        const name = place.name_th
          ? `${place.name_en} (${place.name_th})`
          : place.name_en;
        const url = absolute(
          `/?area=${main.id}&place=${encodeURIComponent(place.id)}`,
        );
        lines.push(`- [${name}](${url}): ${place.description}`);
      }
    }
  }
  lines.push(
    "",
    "## Linking",
    "",
    `- Open a map: ${absolute("/?area=<area id>")}`,
    `- Open a place: ${absolute("/?area=<area id>&place=<place id>")}`,
    "- The search box also accepts coordinates as latitude, longitude (for example 13.7437, 100.4889).",
    "",
    "## Questions",
    "",
    ...STRINGS.en.faq.flatMap(([question, answer]) => [
      `### ${question}`,
      "",
      answer,
      "",
    ]),
    "## Data and licences",
    "",
    "- Map data © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright",
    "- Building heights: Google Open Buildings 2.5D Temporal, CC BY 4.0",
    "- Tree canopy: Meta and World Resources Institute, CC BY 4.0",
    "- Landmark descriptions: Wikidata, CC0",
    ...(REPO_URL ? ["", "## Source", "", `- ${REPO_URL}`] : []),
    `- Sitemap: ${absolute("/sitemap.xml")}`,
    "",
  );
  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

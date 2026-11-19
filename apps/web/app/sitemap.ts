import type { MetadataRoute } from "next";

import { areas, places } from "@/lib/server-data";
import { absolute } from "@/lib/site";

export const revalidate = 3600;

// Next writes <loc> values verbatim, so the query separator is pre-escaped for XML.

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: absolute("/"), changeFrequency: "weekly", priority: 1 },
  ];
  for (const area of await areas()) {
    entries.push({
      url: absolute(`/?area=${area.id}`),
      changeFrequency: "weekly",
      priority: 0.8,
    });
    for (const place of await places(area.id)) {
      entries.push({
        url: absolute(
          `/?area=${area.id}&place=${encodeURIComponent(place.id)}`,
        ),
        changeFrequency: "monthly",
        priority: 0.5,
      });
    }
  }
  return entries;
}

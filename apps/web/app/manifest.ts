import type { MetadataRoute } from "next";

import { DESCRIPTION, SITE_NAME, SITE_NAME_TH } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${SITE_NAME} · ${SITE_NAME_TH}`,
    short_name: SITE_NAME,
    description: DESCRIPTION,
    start_url: "/",
    display: "standalone",
    background_color: "#1c1412",
    theme_color: "#1c1412",
    lang: "th",
    icons: [
      { src: "/icon.png", sizes: "512x512", type: "image/png" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}

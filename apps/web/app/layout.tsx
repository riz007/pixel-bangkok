import type { Metadata, Viewport } from "next";
import { Bai_Jamjuree, Chonburi } from "next/font/google";
import type { ReactNode } from "react";

import { STRINGS } from "@/lib/i18n";
import {
  DESCRIPTION,
  DESCRIPTION_TH,
  KEYWORDS,
  MAKER_NAME,
  REPO_URL,
  SITE_NAME,
  SITE_NAME_TH,
  SITE_URL,
} from "@/lib/site";

import "./globals.css";

const display = Chonburi({
  weight: "400",
  subsets: ["thai", "latin"],
  variable: "--font-display",
  display: "swap",
});

const body = Bai_Jamjuree({
  weight: ["400", "500", "600", "700"],
  subsets: ["thai", "latin"],
  variable: "--font-body",
  display: "swap",
});

const OG_ALT = "Isometric pixel-art map of central Bangkok with the Chao Phraya river";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} · ${SITE_NAME_TH} — isometric pixel-art map of Bangkok`,
    template: `%s · ${SITE_NAME}`,
  },
  description: DESCRIPTION,
  keywords: KEYWORDS,
  applicationName: SITE_NAME,
  category: "travel",
  ...(MAKER_NAME ? { authors: [{ name: MAKER_NAME, url: REPO_URL ?? undefined }] } : {}),
  alternates: {
    canonical: "/",
    languages: { th: "/", en: "/", "x-default": "/" },
  },
  openGraph: {
    title: `${SITE_NAME} · ${SITE_NAME_TH}`,
    description: DESCRIPTION,
    url: "/",
    siteName: SITE_NAME,
    locale: "th_TH",
    alternateLocale: ["en_US"],
    type: "website",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: OG_ALT }],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} · ${SITE_NAME_TH}`,
    description: DESCRIPTION,
    images: [{ url: "/og.png", alt: OG_ALT }],
  },
  robots: { index: true, follow: true, googleBot: { "max-image-preview": "large" } },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1c1412",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th" className={`${display.variable} ${body.variable}`} suppressHydrationWarning>
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData()).replace(/</g, "\\u003c") }}
        />
        {children}
      </body>
    </html>
  );
}

function structuredData() {
  const site = { "@type": "WebSite", "@id": `${SITE_URL}/#website`, url: SITE_URL, name: SITE_NAME };
  const map = {
    "@type": ["Map", "WebApplication"],
    "@id": `${SITE_URL}/#map`,
    name: `${SITE_NAME} · ${SITE_NAME_TH}`,
    alternateName: "พิกเซลกรุงเทพ",
    url: SITE_URL,
    description: DESCRIPTION,
    abstract: DESCRIPTION_TH,
    inLanguage: ["th", "en"],
    applicationCategory: "TravelApplication",
    operatingSystem: "Any (web browser)",
    browserRequirements: "Requires JavaScript",
    isAccessibleForFree: true,
    offers: { "@type": "Offer", price: "0", priceCurrency: "THB" },
    keywords: KEYWORDS.join(", "),
    image: `${SITE_URL}/og.png`,
    spatialCoverage: {
      "@type": "Place",
      name: "Bangkok (Krung Thep Maha Nakhon), Thailand",
      geo: { "@type": "GeoShape", box: "13.67 100.46 13.85 100.65" },
    },
    isBasedOn: [
      { "@type": "Dataset", name: "OpenStreetMap", url: "https://www.openstreetmap.org/copyright", license: "https://opendatacommons.org/licenses/odbl/" },
      { "@type": "Dataset", name: "Google Open Buildings 2.5D Temporal", license: "https://creativecommons.org/licenses/by/4.0/" },
      { "@type": "Dataset", name: "Meta and WRI High Resolution Canopy Height Maps", license: "https://creativecommons.org/licenses/by/4.0/" },
      { "@type": "Dataset", name: "Wikidata", license: "https://creativecommons.org/publicdomain/zero/1.0/" },
    ],
    ...(REPO_URL ? { codeRepository: REPO_URL } : {}),
    ...(MAKER_NAME ? { creator: { "@type": "Person", name: MAKER_NAME } } : {}),
  };
  const faq = {
    "@type": "FAQPage",
    "@id": `${SITE_URL}/#faq`,
    inLanguage: "en",
    mainEntity: STRINGS.en.faq.map(([question, answer]) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
  return { "@context": "https://schema.org", "@graph": [site, map, faq] };
}

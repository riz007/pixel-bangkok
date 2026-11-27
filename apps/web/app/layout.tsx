import type { Metadata, Viewport } from "next";
import { Bai_Jamjuree, Chonburi } from "next/font/google";
import Script from "next/script";
import type { ReactNode } from "react";

import { AnalyticsLoader } from "@/features/map/AnalyticsLoader";
import { ANALYTICS_ENABLED, CONSENT_KEY, GTM_ID } from "@/lib/consent";
import { STRINGS } from "@/lib/i18n";
import {
  DESCRIPTION,
  DESCRIPTION_TH,
  KEYWORDS,
  MAKER_NAME,
  OG_IMAGE_PATH,
  REPO_URL,
  SHORT_DESCRIPTION,
  SITE_NAME,
  SITE_NAME_TH,
  SITE_URL,
  TITLE,
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
    default: TITLE,
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
    description: SHORT_DESCRIPTION,
    url: "/",
    siteName: SITE_NAME,
    locale: "th_TH",
    alternateLocale: ["en_US"],
    type: "website",
    images: [{ url: OG_IMAGE_PATH, width: 1200, height: 630, alt: OG_ALT }],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} · ${SITE_NAME_TH}`,
    description: SHORT_DESCRIPTION,
    images: [{ url: OG_IMAGE_PATH, alt: OG_ALT }],
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
        {ANALYTICS_ENABLED && (
          <>
            <Script id="consent-defaults" strategy="beforeInteractive">
              {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('consent','default',{ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',analytics_storage:'denied',wait_for_update:500});try{if(localStorage.getItem('${CONSENT_KEY}')==='granted'){gtag('consent','update',{analytics_storage:'granted'});}}catch(e){}`}
            </Script>
            <AnalyticsLoader />
          </>
        )}
        {GTM_ID && (
          <>
            <Script id="google-tag-manager" strategy="afterInteractive">
              {`(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','${GTM_ID}');`}
            </Script>
            <noscript>
              <iframe
                title="Google Tag Manager"
                src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`}
                height="0"
                width="0"
                style={{ display: "none", visibility: "hidden" }}
              />
            </noscript>
          </>
        )}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData()).replace(/</g, "\\u003c") }}
        />
        {children}
      </body>
    </html>
  );
}

/** The open datasets the map is built from, as Google's Dataset structured data expects them:
 * every Dataset needs a description, and a creator is recommended. */
const SOURCES = [
  {
    name: "OpenStreetMap",
    description:
      "Collaborative open map of the world. Pixel Bangkok draws its roads, canals, railways, " +
      "landmarks and mapped buildings from it.",
    url: "https://www.openstreetmap.org/copyright",
    license: "https://opendatacommons.org/licenses/odbl/",
    creator: "OpenStreetMap contributors",
    creatorUrl: "https://www.openstreetmap.org/",
  },
  {
    name: "Overture Maps buildings",
    description:
      "Building outlines combining OpenStreetMap with outlines traced from imagery by Google " +
      "and Microsoft. Used for buildings OpenStreetMap has not mapped yet.",
    url: "https://docs.overturemaps.org/attribution/",
    license: "https://opendatacommons.org/licenses/odbl/",
    creator: "Overture Maps Foundation",
    creatorUrl: "https://overturemaps.org/",
  },
  {
    name: "Google Open Buildings 2.5D Temporal",
    description:
      "Satellite-derived building presence and height rasters. Used to estimate the height of " +
      "buildings without a published height.",
    url: "https://sites.research.google/gr/open-buildings/temporal/",
    license: "https://creativecommons.org/licenses/by/4.0/",
    creator: "Google Research",
    creatorUrl: "https://research.google/",
  },
  {
    name: "Meta and WRI High Resolution Canopy Height Maps",
    description:
      "Global tree canopy height at about 1 m resolution. Used to place and size every tree on " +
      "the map.",
    url: "https://registry.opendata.aws/dataforgood-fb-forests/",
    license: "https://creativecommons.org/licenses/by/4.0/",
    creator: "Meta and World Resources Institute",
    creatorUrl: "https://www.wri.org/",
  },
  {
    name: "Wikidata",
    description:
      "Free knowledge base. Used for place names, descriptions and the heights of some towers.",
    url: "https://www.wikidata.org/",
    license: "https://creativecommons.org/publicdomain/zero/1.0/",
    creator: "Wikidata contributors",
    creatorUrl: "https://www.wikidata.org/",
  },
  {
    name: "Open-Meteo weather and air quality",
    description:
      "Modelled current weather and air quality, including PM2.5 from the Copernicus " +
      "Atmosphere Monitoring Service, shown live on the map.",
    url: "https://open-meteo.com/",
    license: "https://creativecommons.org/licenses/by/4.0/",
    creator: "Open-Meteo",
    creatorUrl: "https://open-meteo.com/",
  },
];

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
    image: `${SITE_URL}${OG_IMAGE_PATH}`,
    spatialCoverage: {
      "@type": "Place",
      name: "Bangkok (Krung Thep Maha Nakhon), Thailand",
      geo: { "@type": "GeoShape", box: "13.67 100.46 13.85 100.65" },
    },
    isBasedOn: SOURCES.map((source) => ({
      "@type": "Dataset",
      name: source.name,
      description: source.description,
      url: source.url,
      license: source.license,
      creator: { "@type": "Organization", name: source.creator, url: source.creatorUrl },
    })),
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

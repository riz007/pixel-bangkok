import type { Metadata, Viewport } from "next";
import { Bai_Jamjuree, Chonburi } from "next/font/google";
import type { ReactNode } from "react";

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

export const metadata: Metadata = {
  title: "Pixel Bangkok · กรุงเทพมหานคร",
  description:
    "Explore Bangkok as one isometric pixel-art map: the Grand Palace, Wat Arun, the Chao Phraya, Chinatown and Sukhumvit, drawn from open data, in Thai and English.",
  openGraph: {
    title: "Pixel Bangkok · กรุงเทพมหานคร",
    description:
      "Bangkok as one isometric pixel-art map you can explore street by street, in Thai and English.",
    images: [{ url: "/og.png", width: 1200, height: 630 }],
    locale: "th_TH",
    alternateLocale: ["en_US"],
    type: "website",
  },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1c1412",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th" className={`${display.variable} ${body.variable}`} suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}

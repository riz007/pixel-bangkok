export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"
).replace(/\/+$/, "");
export const SITE_NAME = "Pixel Bangkok";
export const SITE_NAME_TH = "กรุงเทพมหานคร";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || null;
export const MAKER_NAME = process.env.NEXT_PUBLIC_MAKER_NAME || null;

export const TITLE = "Pixel Bangkok · กรุงเทพมหานคร | Pixel-Art City Map";
/** Search snippet, kept under ~155 characters. */
export const DESCRIPTION =
  "Explore Bangkok street by street as an interactive isometric pixel-art map: the Grand Palace, Wat Arun, the Chao Phraya and the BTS, in Thai and English.";
/** Social card text, kept under ~125 characters. */
export const SHORT_DESCRIPTION =
  "Explore Bangkok street by street as an interactive pixel-art map: temples, the river and the BTS, in Thai and English.";
export const OG_IMAGE_PATH = "/og.jpg";

/** Shorten text to `limit` characters at a word boundary, with an ellipsis. */
export function clip(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit - 1);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), limit - 20)).trimEnd()}…`;
}
export const DESCRIPTION_TH =
  "แผนที่กรุงเทพมหานครแบบไอโซเมตริกพิกเซลอาร์ต ซูมเที่ยวได้ทุกตรอกซอกซอย ทั้งพระบรมมหาราชวัง วัดอรุณ แม่น้ำเจ้าพระยา เยาวราช สยาม สุขุมวิท รถไฟฟ้า BTS และ MRT วาดจากข้อมูล OpenStreetMap";

export const KEYWORDS = [
  "Bangkok map",
  "pixel art map",
  "isometric map",
  "interactive map of Bangkok",
  "Krung Thep Maha Nakhon",
  "Bangkok full name",
  "Grand Palace",
  "Wat Arun",
  "Chao Phraya",
  "BTS Skytrain",
  "แผนที่กรุงเทพ",
  "กรุงเทพมหานคร",
  "แผนที่พิกเซล",
];

/** Absolute URL for a site path. */
export function absolute(path: string): string {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Absolute base for published map files, for server-side fetches. */
export function assetsBase(): string {
  const base = (process.env.NEXT_PUBLIC_MAP_ASSETS_URL ?? "/maps").replace(
    /\/+$/,
    "",
  );
  return base.startsWith("http") ? base : absolute(base);
}

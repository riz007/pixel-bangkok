export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"
).replace(/\/+$/, "");
export const SITE_NAME = "Pixel Bangkok";
export const SITE_NAME_TH = "กรุงเทพมหานคร";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || null;
export const MAKER_NAME = process.env.NEXT_PUBLIC_MAKER_NAME || null;

export const DESCRIPTION =
  "An interactive isometric pixel-art map of Bangkok: the Grand Palace, Wat Arun, the Chao Phraya, Chinatown, Siam, Sukhumvit, the BTS and MRT, drawn from OpenStreetMap in Thai and English.";
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

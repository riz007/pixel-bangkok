export type Lang = "th" | "en";

export const LANGS: Lang[] = ["th", "en"];

const en = {
  appName: "Pixel Bangkok",
  cityName: "Bangkok",
  searchLabel: "Search places in Thai or English",
  searchPlaceholder: "A place, or lat, long",
  goToCoordinate: (lat: string, lon: string) => `Go to ${lat}, ${lon}`,
  outsideMap: "That point is outside this map area.",
  searchedLocation: "Searched location",
  report: "Report",
  reportLabel: "Report a map error on OpenStreetMap, at this view",
  fullscreen: "Full screen",
  exitFullscreen: "Exit full screen",
  northArrow: "North arrow",
  searchNoResults: "No places match. Try a Thai or English name.",
  resultsCount: (n: number) => (n === 1 ? "1 place found" : `${n} places found`),
  places: "Places",
  aiArt: "AI art",
  labels: "Labels",
  traffic: "Traffic",
  share: "Share",
  about: "About",
  language: "ภาษาไทย",
  languageLabel: "Switch to Thai",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  home: "Show all of Bangkok",
  mapArea: "Map area",
  mapTools: "Map tools",
  zoomGroup: "Zoom",
  placesRail: "Places to visit, in walking order",
  previousPlace: "Previous place",
  nextPlace: "Next place",
  placeOf: (index: number, total: number) => `${index} of ${total}`,
  close: "Close",
  coordinates: "Coordinates",
  source: "Source",
  readMore: "Read more",
  linkCopied: "Link copied",
  loadingMap: "Loading the map",
  loadingTiles: "Drawing the city",
  mapUnavailable: "The map could not be loaded",
  mapUnavailableHint:
    "Map files are missing or unreachable. Check your connection and try again.",
  tryAgain: "Try again",
  tilesFailed: "Some parts of the map did not load and may look blurry.",
  aboutTitle: "About this map",
  aboutIntro:
    "Bangkok as one pixel-art map you can explore street by street: temples, canals, markets and the river, drawn from open data.",
  fullNameLabel: "The city's full ceremonial name",
  fullNameMeaning:
    "City of angels, great city of immortals, magnificent city of the nine gems, seat of the king, city of royal palaces, home of gods incarnate, erected by Vishvakarman at Indra's behest.",
  howMadeTitle: "How it was made",
  howMade:
    "Every building, road, canal and tree comes from OpenStreetMap, with heights from Google Open Buildings and trees from a canopy map. A program draws them as an isometric map, so every place is where it really is.",
  aiNote: (model: string, coverage: number) =>
    `Where the map looks hand-painted, it was redrawn by ${model}, an AI image model, over ${coverage}% of the area. It can invent small details such as rooftop clutter, people and cars, so every AI tile is checked against the plain drawing and discarded if anything moved. Switch off AI art to see the plain drawing.`,
  shortcutsTitle: "Keyboard shortcuts",
  dataTitle: "Data and credits",
  madeBy: (name: string) => `Made by ${name}`,
  shortcuts: [
    ["/", "Search places or lat, long"],
    ["P", "Show or hide places"],
    ["A", "AI art on or off"],
    ["L", "Labels on or off"],
    ["T", "Traffic and boats on or off"],
    ["F", "Full screen"],
    ["+ / −", "Zoom"],
    ["Esc", "Close"],
  ] as [string, string][],
  aiOnLabel: "Show the plain drawing",
  aiOffLabel: "Show AI art",
  trafficOnLabel: "Pause traffic and boats",
  trafficOffLabel: "Play traffic and boats",
};

type Strings = typeof en;

const th: Strings = {
  appName: "Pixel Bangkok",
  cityName: "กรุงเทพมหานคร",
  searchLabel: "ค้นหาสถานที่ ภาษาไทยหรืออังกฤษ",
  searchPlaceholder: "สถานที่ หรือ ละติจูด, ลองจิจูด",
  goToCoordinate: (lat: string, lon: string) => `ไปที่ ${lat}, ${lon}`,
  outsideMap: "พิกัดนี้อยู่นอกพื้นที่แผนที่",
  searchedLocation: "ตำแหน่งที่ค้นหา",
  report: "แจ้งแก้",
  reportLabel: "แจ้งข้อมูลแผนที่ผิดบน OpenStreetMap ณ ตำแหน่งนี้",
  fullscreen: "เต็มจอ",
  exitFullscreen: "ออกจากเต็มจอ",
  northArrow: "ทิศเหนือ",
  searchNoResults: "ไม่พบสถานที่ ลองพิมพ์ชื่อภาษาไทยหรืออังกฤษ",
  resultsCount: (n: number) => `พบ ${n} แห่ง`,
  places: "สถานที่",
  aiArt: "ภาพ AI",
  labels: "ป้ายชื่อ",
  traffic: "การจราจร",
  share: "แชร์",
  about: "เกี่ยวกับ",
  language: "English",
  languageLabel: "Switch to English",
  zoomIn: "ซูมเข้า",
  zoomOut: "ซูมออก",
  home: "ดูกรุงเทพฯ ทั้งหมด",
  mapArea: "พื้นที่แผนที่",
  mapTools: "เครื่องมือแผนที่",
  zoomGroup: "ซูม",
  placesRail: "สถานที่น่าเที่ยว เรียงตามเส้นทางเดิน",
  previousPlace: "สถานที่ก่อนหน้า",
  nextPlace: "สถานที่ถัดไป",
  placeOf: (index: number, total: number) => `${index} จาก ${total}`,
  close: "ปิด",
  coordinates: "พิกัด",
  source: "แหล่งข้อมูล",
  readMore: "อ่านเพิ่มเติม",
  linkCopied: "คัดลอกลิงก์แล้ว",
  loadingMap: "กำลังโหลดแผนที่",
  loadingTiles: "กำลังวาดเมือง",
  mapUnavailable: "โหลดแผนที่ไม่สำเร็จ",
  mapUnavailableHint: "ไม่พบไฟล์แผนที่หรือเชื่อมต่อไม่ได้ ตรวจสอบอินเทอร์เน็ตแล้วลองอีกครั้ง",
  tryAgain: "ลองอีกครั้ง",
  tilesFailed: "บางส่วนของแผนที่โหลดไม่สำเร็จ อาจดูไม่คมชัด",
  aboutTitle: "เกี่ยวกับแผนที่นี้",
  aboutIntro:
    "กรุงเทพฯ ทั้งเมืองในภาพพิกเซลอาร์ตที่ซูมเที่ยวได้ทุกตรอกซอกซอย ทั้งวัด คลอง ตลาด และแม่น้ำเจ้าพระยา วาดจากข้อมูลเปิด",
  fullNameLabel: "ชื่อเต็มของกรุงเทพมหานคร",
  fullNameMeaning:
    "ชื่อเมืองที่ยาวที่สุดในโลก ได้รับการบันทึกโดยกินเนสส์เวิลด์เรคคอร์ด",
  howMadeTitle: "แผนที่นี้ทำอย่างไร",
  howMade:
    "อาคาร ถนน คลอง และต้นไม้ทุกแห่งมาจาก OpenStreetMap ความสูงอาคารจาก Google Open Buildings และต้นไม้จากแผนที่ความสูงเรือนยอด โปรแกรมวาดทั้งหมดเป็นแผนที่ไอโซเมตริก ทุกสถานที่จึงอยู่ตรงตำแหน่งจริง",
  aiNote: (model: string, coverage: number) =>
    `ส่วนที่ดูเหมือนภาพวาดมือ วาดใหม่ด้วย ${model} ซึ่งเป็นโมเดลสร้างภาพด้วย AI ครอบคลุม ${coverage}% ของพื้นที่ AI อาจเติมรายละเอียดเล็ก ๆ เช่น ของบนดาดฟ้า ผู้คน และรถ ทุกภาพจึงถูกตรวจเทียบกับภาพวาดต้นฉบับ และตัดทิ้งหากตำแหน่งเคลื่อน ปิดภาพ AI เพื่อดูภาพวาดต้นฉบับได้`,
  shortcutsTitle: "ปุ่มลัด",
  dataTitle: "ข้อมูลและเครดิต",
  madeBy: (name: string) => `สร้างโดย ${name}`,
  shortcuts: [
    ["/", "ค้นหาสถานที่หรือพิกัด"],
    ["P", "แสดงหรือซ่อนสถานที่"],
    ["A", "เปิดหรือปิดภาพ AI"],
    ["L", "เปิดหรือปิดป้ายชื่อ"],
    ["T", "เปิดหรือปิดรถและเรือ"],
    ["F", "เต็มจอ"],
    ["+ / −", "ซูม"],
    ["Esc", "ปิด"],
  ],
  aiOnLabel: "ดูภาพวาดต้นฉบับ",
  aiOffLabel: "ดูภาพ AI",
  trafficOnLabel: "หยุดรถและเรือ",
  trafficOffLabel: "เล่นรถและเรือ",
};

export const STRINGS: Record<Lang, Strings> = { th, en };

export const FULL_NAME_TH =
  "กรุงเทพมหานคร อมรรัตนโกสินทร์ มหินทรายุธยา มหาดิลกภพ นพรัตนราชธานีบูรีรมย์ อุดมราชนิเวศน์มหาสถาน อมรพิมานอวตารสถิต สักกะทัตติยวิษณุกรรมประสิทธิ์";

export const FULL_NAME_ROMAN =
  "Krung Thep Mahanakhon Amon Rattanakosin Mahinthara Ayuthaya Mahadilok Phop Noppharat Ratchathani Burirom Udomratchaniwet Mahasathan Amon Piman Awatan Sathit Sakkathattiya Witsanukam Prasit";

export function detectLang(languages: readonly string[]): Lang {
  return languages.some((code) => code.toLowerCase().startsWith("th")) ? "th" : "en";
}

export function placeName(poi: { nameEn: string; nameTh: string | null }, lang: Lang) {
  const primary = lang === "th" && poi.nameTh ? poi.nameTh : poi.nameEn;
  const secondary = lang === "th" ? poi.nameEn : poi.nameTh;
  return { primary, secondary: secondary && secondary !== primary ? secondary : null };
}

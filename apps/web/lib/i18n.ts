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
  sourceCode: "Source code on GitHub",
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
  filterLabel: "Show places by type",
  filterAll: "All",
  consentTitle: "Cookies",
  consentText:
    "May we use analytics cookies to count visits and improve the map? Nothing is stored until you allow it.",
  consentAllow: "Allow",
  consentDecline: "Decline",
  privacySettings: "Privacy settings",
  privacyLink: "Privacy notice",
  privacyTitle: "Privacy notice",
  privacyUpdated: "Last updated 19 November 2026",
  privacyWho: (maker: string | null, hasContact: boolean) =>
    `Pixel Bangkok${maker ? `, run by ${maker},` : ""} is responsible for the personal data described here (the data controller under Thailand's Personal Data Protection Act).${hasContact ? " Contact:" : ""}`,
  privacyAnalytics:
    "Analytics (only if you choose Allow): Google Analytics is loaded only after you allow it and sets cookies to count visits and see which places and features are used, along with your device type, browser and approximate location. It is kept for up to 14 months. The legal basis is your consent, which you can withdraw at any time in Privacy settings.",
  privacyHosting:
    "Hosting: to deliver the site and keep it secure, Vercel and Cloudflare process your IP address and request details in short-lived server logs. The legal basis is our legitimate interest in running the site.",
  privacyNone:
    "There are no accounts or forms, and we do not sell personal data. Your language and cookie choices are saved only in your own browser.",
  privacyTransfer:
    "Google, Vercel and Cloudflare may process data outside Thailand under their own data protection safeguards.",
  privacyRights:
    "You can ask to access, correct or delete your data, object to its use, or withdraw consent. You can also complain to Thailand's Personal Data Protection Committee (PDPC).",
  faqTitle: "Questions",
  faq: [
    [
      "What is Pixel Bangkok?",
      "An interactive isometric pixel-art map of Bangkok you can pan, zoom and search, with temples, canals, markets, the Chao Phraya, the BTS and MRT, in Thai and English.",
    ],
    [
      "Is the map geographically accurate?",
      "Yes. Every building, road, canal, railway and tree is placed from OpenStreetMap and drawn with one fixed isometric projection, so places keep their real positions and distances. Building heights come from Google Open Buildings or OpenStreetMap; where none is known, a default height is used and recorded.",
    ],
    [
      "Which parts of Bangkok does it cover?",
      "A 20 by 20 km map of central Bangkok from Chatuchak to Sathon and both banks of the river, plus detailed maps of Inner Bangkok, the old town of Rattanakosin and Wat Arun.",
    ],
    [
      "Is AI used?",
      "Optionally. Parts of the map can be shown repainted by an open image model for a hand-drawn look; every AI tile is checked against the plain drawing and discarded if anything moved. The plain drawing is always one click away.",
    ],
    [
      "Is it free to use?",
      "Yes. It is free and needs no account. If you allow it, visits are measured with Google Analytics. Map data is © OpenStreetMap contributors under the ODbL.",
    ],
  ] as [string, string][],
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
  sourceCode: "ซอร์สโค้ดบน GitHub",
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
  filterLabel: "แสดงสถานที่ตามประเภท",
  filterAll: "ทั้งหมด",
  consentTitle: "คุกกี้",
  consentText:
    "ขออนุญาตใช้คุกกี้วิเคราะห์เพื่อนับการเข้าชมและปรับปรุงแผนที่ จะไม่มีการจัดเก็บใด ๆ จนกว่าคุณจะอนุญาต",
  consentAllow: "อนุญาต",
  consentDecline: "ไม่อนุญาต",
  privacySettings: "ตั้งค่าความเป็นส่วนตัว",
  privacyLink: "ประกาศความเป็นส่วนตัว",
  privacyTitle: "ประกาศความเป็นส่วนตัว",
  privacyUpdated: "ปรับปรุงล่าสุด 19 พฤศจิกายน 2569",
  privacyWho: (maker: string | null, hasContact: boolean) =>
    `Pixel Bangkok${maker ? ` ซึ่งดำเนินการโดย ${maker}` : ""} เป็นผู้ควบคุมข้อมูลส่วนบุคคลที่ระบุไว้ในประกาศนี้ ตามพระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562${hasContact ? " ติดต่อ:" : ""}`,
  privacyAnalytics:
    "การวิเคราะห์การใช้งาน (เฉพาะเมื่อคุณกดอนุญาต): Google Analytics จะโหลดหลังจากคุณอนุญาตเท่านั้น และจะตั้งคุกกี้เพื่อนับการเข้าชมและดูว่ามีการใช้สถานที่และฟีเจอร์ใดบ้าง รวมถึงประเภทอุปกรณ์ เบราว์เซอร์ และตำแหน่งโดยประมาณ ข้อมูลจะเก็บไว้ไม่เกิน 14 เดือน ฐานทางกฎหมายคือความยินยอมของคุณ ซึ่งถอนได้ทุกเมื่อในตั้งค่าความเป็นส่วนตัว",
  privacyHosting:
    "การให้บริการเว็บไซต์: Vercel และ Cloudflare ประมวลผลที่อยู่ IP และรายละเอียดการเข้าใช้งานในบันทึกของเซิร์ฟเวอร์ที่เก็บไว้ช่วงสั้น ๆ เพื่อให้บริการเว็บไซต์และรักษาความปลอดภัย ฐานทางกฎหมายคือประโยชน์โดยชอบด้วยกฎหมายในการดำเนินงานเว็บไซต์",
  privacyNone:
    "เว็บไซต์นี้ไม่มีระบบสมาชิกหรือแบบฟอร์ม และไม่ขายข้อมูลส่วนบุคคล การตั้งค่าภาษาและคุกกี้ของคุณจะถูกบันทึกไว้ในเบราว์เซอร์ของคุณเท่านั้น",
  privacyTransfer:
    "Google, Vercel และ Cloudflare อาจประมวลผลข้อมูลนอกประเทศไทย ภายใต้มาตรการคุ้มครองข้อมูลของผู้ให้บริการแต่ละราย",
  privacyRights:
    "คุณมีสิทธิขอเข้าถึง แก้ไข หรือลบข้อมูล คัดค้านการใช้ข้อมูล หรือถอนความยินยอม และสามารถร้องเรียนต่อสำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล (สคส.)",
  faqTitle: "คำถามที่พบบ่อย",
  faq: [
    [
      "Pixel Bangkok คืออะไร",
      "แผนที่กรุงเทพฯ แบบไอโซเมตริกพิกเซลอาร์ตที่เลื่อน ซูม และค้นหาได้ ทั้งวัด คลอง ตลาด แม่น้ำเจ้าพระยา รถไฟฟ้า BTS และ MRT รองรับภาษาไทยและอังกฤษ",
    ],
    [
      "แผนที่ถูกต้องตามจริงไหม",
      "ถูกต้องตามตำแหน่งจริง อาคาร ถนน คลอง ทางรถไฟ และต้นไม้ทุกแห่งวางจากข้อมูล OpenStreetMap และวาดด้วยมุมมองไอโซเมตริกเดียวกันทั้งหมด ความสูงอาคารมาจาก Google Open Buildings หรือ OpenStreetMap หากไม่มีข้อมูลจะใช้ความสูงมาตรฐานและบันทึกไว้",
    ],
    [
      "ครอบคลุมพื้นที่ไหนบ้าง",
      "แผนที่ใจกลางกรุงเทพฯ ขนาด 20 x 20 กม. ตั้งแต่จตุจักรถึงสาทรและสองฝั่งแม่น้ำ พร้อมแผนที่ละเอียดของกรุงเทพฯ ชั้นใน เกาะรัตนโกสินทร์ และวัดอรุณ",
    ],
    [
      "ใช้ AI หรือเปล่า",
      "ใช้เป็นตัวเลือก บางส่วนของแผนที่แสดงภาพที่วาดใหม่ด้วยโมเดลสร้างภาพแบบเปิด ทุกภาพถูกตรวจเทียบกับภาพวาดต้นฉบับและตัดทิ้งหากตำแหน่งเคลื่อน กดปิดภาพ AI ได้ทุกเมื่อ",
    ],
    [
      "ใช้ฟรีไหม",
      "ใช้ฟรีและไม่ต้องสมัครสมาชิก หากคุณอนุญาต จะมีการวัดสถิติการเข้าชมด้วย Google Analytics ข้อมูลแผนที่ © ผู้ร่วมพัฒนา OpenStreetMap ภายใต้สัญญาอนุญาต ODbL",
    ],
  ],
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

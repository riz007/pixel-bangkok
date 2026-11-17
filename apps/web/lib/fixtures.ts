export function manifestFixture() {
  return {
    version: 2,
    area_id: "test-area",
    name: { en: "Test area", th: "พื้นที่ทดสอบ" },
    image: { width: 1000, height: 300 },
    tiles: {
      tile_size: 256,
      overlap: 1,
      format: "webp",
      url_template: "tiles/{level}/{column}_{row}.{format}",
      min_level: 0,
      max_level: 10,
      levels: [
        { level: 9, width: 500, height: 150, columns: 2, rows: 1 },
        { level: 10, width: 1000, height: 300, columns: 4, rows: 2 },
      ],
    },
    attributions: [
      {
        text: "© OpenStreetMap contributors",
        url: "https://www.openstreetmap.org/copyright",
        licence: "ODbL 1.0",
        provider: "OpenStreetMap",
      },
      {
        text: "Building heights: Google Open Buildings 2.5D Temporal",
        url: "https://sites.research.google/gr/open-buildings/temporal/",
        licence: "CC BY 4.0",
        provider: "Google Open Buildings 2.5D Temporal",
      },
    ],
    source: { dataset: "OpenStreetMap via Overpass API", retrieved_at: "2026-01-01T00:00:00+00:00" },
  };
}

export function poisFixture() {
  return {
    area_id: "test-area",
    pois: [
      {
        id: "prang",
        name_en: "Wat Arun Central Prang",
        name_th: "พระปรางค์วัดอรุณ",
        aliases: ["Temple of Dawn", "วัดแจ้ง"],
        category: "temple",
        lon: 100.48889,
        lat: 13.7437,
        description: "Central tower.",
        source: "OpenStreetMap way 1",
        source_url: "https://www.openstreetmap.org/way/1",
        image: { x: 500, y: 150 },
      },
      {
        id: "pier",
        name_en: "Tha Tien Pier",
        name_th: "ท่าเตียน",
        aliases: ["Tha Tian"],
        category: "pier",
        lon: 100.49035,
        lat: 13.74578,
        description: "Pier.",
        image: { x: 1000, y: 300 },
      },
    ],
  };
}

/** Fits computed by the pipeline (MapBounds.browser_transforms) for the pytest test area. */
const GEOGRAPHIC = {"lonlat_to_world": {"origin": [100.48969999910044, 13.74370000078001], "x": [99.99999999976139, 108142.03017639264, -683.505009873521, 21.917303016691502, -459.3081408362717, -24.413490871226795], "y": [50.00000000002777, 668.157055485354, 110626.11522094508, 224.49727326608374, 44.84155247903938, 4.17307692761797], "max_error_m": 3.781748327682691e-09}, "world_to_lonlat": {"origin": [100.0, 50.0], "lon": [100.48969999910045, 9.246745467843787e-06, 5.7131146961712656e-08, -2.0609191503845098e-14, 3.5430085352786544e-13, 2.0591118388085163e-14], "lat": [13.743700000780011, -5.584827969535137e-08, 9.0391118355512e-06, -1.731776224125469e-13, -3.81237415542646e-14, -3.4250230130412714e-15], "max_error_m": 1.2879554821121814e-08}};

export const GEOGRAPHIC_PROBE = {"world": [37, 81], "lonlat": [100.48911922444756, 13.743983731072353]};

export function manifestFixture() {
  return {
    version: 3,
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
    projection: {
      camera: { azimuth_deg: 315, elevation_deg: 30 },
      pixels_per_metre: 3,
      world_to_image: { px: [2.1, 2.1, 0, 10], py: [-0.75, 0.75, -2.6, 200] },
      bounds: { width_m: 200, height_m: 100 },
      geographic: GEOGRAPHIC,
    },
    animation: {
      overlay_url_template: "overlay/{level}/{column}_{row}.{format}",
      motion_url: "motion.json",
    },
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

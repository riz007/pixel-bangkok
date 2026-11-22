export class DataError extends Error {}

export interface TileLevel {
  level: number;
  width: number;
  height: number;
  columns: number;
  rows: number;
}

export interface TileManifest {
  version: number;
  areaId: string;
  name: { en: string; th: string | null };
  image: { width: number; height: number };
  tiles: {
    tileSize: number;
    overlap: number;
    format: string;
    urlTemplate: string;
    minLevel: number;
    maxLevel: number;
    levels: TileLevel[];
    present: Record<string, Record<number, string>>;
  };
  attributions: Attribution[];
  projection: {
    worldToImage: { px: number[]; py: number[] };
    cameraAzimuthDeg: number;
    pixelsPerMetre: number;
    geographic: GeographicTransforms | null;
  };
  animation: {
    overlayUrlTemplate: string | null;
    frontUrlTemplate: string | null;
    motionUrl: string | null;
  } | null;
  ai: {
    urlTemplate: string;
    overlayUrlTemplate: string | null;
    frontOverlayUrlTemplate: string | null;
    model: string;
    licence: string;
    coverage: number;
    focus: { lon: number; lat: number } | null;
    version: string;
  } | null;
  source: { dataset: string; retrievedAt: string | null };
  contentVersion: string;
}

export interface QuadraticFit {
  origin: [number, number];
  first: number[];
  second: number[];
}

export interface GeographicTransforms {
  widthM: number;
  heightM: number;
  lonLatToWorld: QuadraticFit;
  worldToLonLat: QuadraticFit;
}

export interface Attribution {
  text: string;
  url: string;
  licence: string;
  provider: string;
}

export interface PointOfInterest {
  id: string;
  nameEn: string;
  nameTh: string | null;
  aliases: string[];
  category: string;
  lon: number;
  lat: number;
  description: string;
  source: string | null;
  sourceUrl: string | null;
  rank: number | null;
  thumbnail: string | null;
  line: StationLine | null;
  image: { x: number; y: number };
}

export interface StationLine {
  en: string;
  th: string;
  code: string;
}

export interface AreaSummary {
  id: string;
  name: { en: string; th: string | null };
}

export const SUPPORTED_MANIFEST_VERSION = 3;

type Json = Record<string, unknown>;

function object(value: unknown, context: string): Json {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new DataError(`${context} must be an object`);
  }
  return value as Json;
}

function text(source: Json, key: string, context: string): string {
  const value = source[key];
  if (typeof value !== "string" || value === "") {
    throw new DataError(`${context}.${key} must be a non-empty string`);
  }
  return value;
}

function optionalText(
  source: Json,
  key: string,
  context: string,
): string | null {
  const value = source[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "string")
    throw new DataError(`${context}.${key} must be a string`);
  return value;
}

function number(source: Json, key: string, context: string): number {
  const value = source[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new DataError(`${context}.${key} must be a finite number`);
  }
  return value;
}

function positiveInteger(source: Json, key: string, context: string): number {
  const value = number(source, key, context);
  if (!Number.isInteger(value) || value < 1) {
    throw new DataError(`${context}.${key} must be a positive integer`);
  }
  return value;
}

function nonNegativeInteger(
  source: Json,
  key: string,
  context: string,
): number {
  const value = number(source, key, context);
  if (!Number.isInteger(value) || value < 0) {
    throw new DataError(`${context}.${key} must be a non-negative integer`);
  }
  return value;
}

function list(source: Json, key: string, context: string): unknown[] {
  const value = source[key];
  if (!Array.isArray(value))
    throw new DataError(`${context}.${key} must be an array`);
  return value;
}

function parseName(
  value: unknown,
  context: string,
): { en: string; th: string | null } {
  const name = object(value, context);
  return {
    en: text(name, "en", context),
    th: optionalText(name, "th", context),
  };
}

function coefficients(
  value: Json,
  key: string,
  context: string,
  count: number,
): number[] {
  const values = list(value, key, context);
  if (
    values.length !== count ||
    !values.every((v) => typeof v === "number" && Number.isFinite(v))
  ) {
    throw new DataError(`${context}.${key} must be ${count} numbers`);
  }
  return values as number[];
}

function parseFit(
  value: unknown,
  keys: [string, string],
  context: string,
): QuadraticFit {
  const fit = object(value, context);
  const [x = 0, y = 0] = coefficients(fit, "origin", context, 2);
  return {
    origin: [x, y],
    first: coefficients(fit, keys[0], context, 6),
    second: coefficients(fit, keys[1], context, 6),
  };
}

function parseGeographic(projection: Json): GeographicTransforms {
  const context = "manifest.projection.geographic";
  const geographic = object(projection.geographic, context);
  const bounds = object(projection.bounds, "manifest.projection.bounds");
  return {
    widthM: number(bounds, "width_m", "manifest.projection.bounds"),
    heightM: number(bounds, "height_m", "manifest.projection.bounds"),
    lonLatToWorld: parseFit(
      geographic.lonlat_to_world,
      ["x", "y"],
      `${context}.lonlat_to_world`,
    ),
    worldToLonLat: parseFit(
      geographic.world_to_lonlat,
      ["lon", "lat"],
      `${context}.world_to_lonlat`,
    ),
  };
}

function parsePresent(value: unknown): Record<string, Record<number, string>> {
  if (value === undefined) return {};
  const layers = object(value, "manifest.tiles.present");
  const result: Record<string, Record<number, string>> = {};
  for (const [layer, levels] of Object.entries(layers)) {
    const entries = object(levels, `manifest.tiles.present.${layer}`);
    result[layer] = {};
    for (const [level, bits] of Object.entries(entries)) {
      if (typeof bits !== "string") {
        throw new DataError(
          `manifest.tiles.present.${layer}.${level} must be a string`,
        );
      }
      result[layer][Number(level)] = bits;
    }
  }
  return result;
}

export function parseManifest(input: unknown): TileManifest {
  const root = object(input, "manifest");
  const version = number(root, "version", "manifest");
  if (version !== SUPPORTED_MANIFEST_VERSION) {
    throw new DataError(`unsupported manifest version ${version}`);
  }
  const image = object(root.image, "manifest.image");
  const tiles = object(root.tiles, "manifest.tiles");
  const attributions = list(root, "attributions", "manifest").map(
    (entry, index) => {
      const context = `manifest.attributions[${index}]`;
      const attribution = object(entry, context);
      return {
        text: text(attribution, "text", context),
        url: text(attribution, "url", context),
        licence: text(attribution, "licence", context),
        provider: text(attribution, "provider", context),
      };
    },
  );
  if (attributions.length === 0)
    throw new DataError("manifest.attributions must not be empty");
  const projection = object(root.projection, "manifest.projection");
  const matrix = object(
    projection.world_to_image,
    "manifest.projection.world_to_image",
  );
  const row = (key: "px" | "py") => {
    const values = list(matrix, key, "manifest.projection.world_to_image");
    if (
      values.length !== 4 ||
      !values.every((v) => typeof v === "number" && Number.isFinite(v))
    ) {
      throw new DataError(
        `manifest.projection.world_to_image.${key} must be four numbers`,
      );
    }
    return values as number[];
  };
  const camera = object(projection.camera, "manifest.projection.camera");
  const geographic =
    projection.geographic === undefined ? null : parseGeographic(projection);
  const animationValue = root.animation;
  const animation =
    animationValue === undefined
      ? null
      : (() => {
          const value = object(animationValue, "manifest.animation");
          return {
            overlayUrlTemplate: optionalText(
              value,
              "overlay_url_template",
              "manifest.animation",
            ),
            frontUrlTemplate: optionalText(
              value,
              "front_url_template",
              "manifest.animation",
            ),
            motionUrl: optionalText(value, "motion_url", "manifest.animation"),
          };
        })();
  const ai =
    root.ai === undefined
      ? null
      : (() => {
          const value = object(root.ai, "manifest.ai");
          return {
            urlTemplate: text(value, "url_template", "manifest.ai"),
            overlayUrlTemplate: optionalText(
              value,
              "overlay_url_template",
              "manifest.ai",
            ),
            frontOverlayUrlTemplate: optionalText(
              value,
              "front_overlay_url_template",
              "manifest.ai",
            ),
            model: text(value, "model", "manifest.ai"),
            licence: text(value, "licence", "manifest.ai"),
            coverage: number(value, "coverage", "manifest.ai"),
            focus:
              value.focus == null
                ? null
                : {
                    lon: number(
                      object(value.focus, "manifest.ai.focus"),
                      "lon",
                      "manifest.ai.focus",
                    ),
                    lat: number(
                      object(value.focus, "manifest.ai.focus"),
                      "lat",
                      "manifest.ai.focus",
                    ),
                  },
            version: (
              optionalText(value, "composed_at", "manifest.ai") ?? "ai"
            ).replace(/\D/g, ""),
          };
        })();
  const source = object(root.source, "manifest.source");
  const levels = list(tiles, "levels", "manifest.tiles").map((entry, index) => {
    const context = `manifest.tiles.levels[${index}]`;
    const level = object(entry, context);
    return {
      level: nonNegativeInteger(level, "level", context),
      width: positiveInteger(level, "width", context),
      height: positiveInteger(level, "height", context),
      columns: positiveInteger(level, "columns", context),
      rows: positiveInteger(level, "rows", context),
    };
  });
  const minLevel = nonNegativeInteger(tiles, "min_level", "manifest.tiles");
  const maxLevel = nonNegativeInteger(tiles, "max_level", "manifest.tiles");
  if (minLevel > maxLevel)
    throw new DataError("manifest.tiles.min_level exceeds max_level");
  const width = positiveInteger(image, "width", "manifest.image");
  const height = positiveInteger(image, "height", "manifest.image");
  const top = levels.find((entry) => entry.level === maxLevel);
  if (!top || top.width !== width || top.height !== height) {
    throw new DataError(
      "manifest top level does not match the image dimensions",
    );
  }
  return {
    version,
    areaId: text(root, "area_id", "manifest"),
    name: parseName(root.name, "manifest.name"),
    image: { width, height },
    tiles: {
      tileSize: positiveInteger(tiles, "tile_size", "manifest.tiles"),
      overlap: nonNegativeInteger(tiles, "overlap", "manifest.tiles"),
      format: text(tiles, "format", "manifest.tiles"),
      urlTemplate: text(tiles, "url_template", "manifest.tiles"),
      minLevel,
      maxLevel,
      levels,
      present: parsePresent(tiles.present),
    },
    attributions,
    projection: {
      worldToImage: { px: row("px"), py: row("py") },
      cameraAzimuthDeg: number(
        camera,
        "azimuth_deg",
        "manifest.projection.camera",
      ),
      pixelsPerMetre: number(
        projection,
        "pixels_per_metre",
        "manifest.projection",
      ),
      geographic,
    },
    animation,
    ai,
    contentVersion: (() => {
      const generated = root.generated;
      if (typeof generated !== "object" || generated === null) return "0";
      const hash = (generated as Json).master_sha256;
      return typeof hash === "string" ? hash.slice(0, 12) : "0";
    })(),
    source: {
      dataset: text(source, "dataset", "manifest.source"),
      retrievedAt: optionalText(source, "retrieved_at", "manifest.source"),
    },
  };
}

export function parsePois(
  input: unknown,
  manifest: TileManifest,
): PointOfInterest[] {
  const root = object(input, "pois");
  const seen = new Set<string>();
  return list(root, "pois", "pois").map((entry, index) => {
    const context = `pois[${index}]`;
    const poi = object(entry, context);
    const image = object(poi.image, `${context}.image`);
    const x = number(image, "x", `${context}.image`);
    const y = number(image, "y", `${context}.image`);
    if (
      x < 0 ||
      y < 0 ||
      x > manifest.image.width ||
      y > manifest.image.height
    ) {
      throw new DataError(`${context}.image lies outside the map image`);
    }
    const id = text(poi, "id", context);
    if (seen.has(id)) throw new DataError(`duplicate POI id '${id}'`);
    seen.add(id);
    const aliases =
      poi.aliases === undefined ? [] : list(poi, "aliases", context);
    if (!aliases.every((alias): alias is string => typeof alias === "string")) {
      throw new DataError(`${context}.aliases must be strings`);
    }
    return {
      id,
      nameEn: text(poi, "name_en", context),
      nameTh: optionalText(poi, "name_th", context),
      aliases,
      category: text(poi, "category", context),
      lon: number(poi, "lon", context),
      lat: number(poi, "lat", context),
      description: typeof poi.description === "string" ? poi.description : "",
      source: optionalText(poi, "source", context),
      sourceUrl: optionalText(poi, "source_url", context),
      rank:
        typeof poi.rank === "number" && Number.isFinite(poi.rank)
          ? poi.rank
          : null,
      thumbnail: optionalText(poi, "thumbnail", context),
      line: poi.line == null ? null : stationLine(poi.line, `${context}.line`),
      image: { x, y },
    };
  });
}

function stationLine(input: unknown, context: string): StationLine {
  const line = object(input, context);
  const code = optionalText(line, "code", context) ?? "";
  return { en: text(line, "en", context), th: text(line, "th", context), code };
}

export function parseAreaIndex(input: unknown): AreaSummary[] {
  const root = object(input, "index");
  return list(root, "areas", "index").map((entry, index) => {
    const context = `index.areas[${index}]`;
    const area = object(entry, context);
    return {
      id: text(area, "id", context),
      name: parseName(area.name, `${context}.name`),
    };
  });
}

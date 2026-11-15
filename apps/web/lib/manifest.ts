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
  };
  attribution: { text: string; url: string; licence: string; provider: string };
  source: { dataset: string; retrievedAt: string | null };
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
  image: { x: number; y: number };
}

export interface AreaSummary {
  id: string;
  name: { en: string; th: string | null };
}

export const SUPPORTED_MANIFEST_VERSION = 1;

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

function optionalText(source: Json, key: string, context: string): string | null {
  const value = source[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") throw new DataError(`${context}.${key} must be a string`);
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

function nonNegativeInteger(source: Json, key: string, context: string): number {
  const value = number(source, key, context);
  if (!Number.isInteger(value) || value < 0) {
    throw new DataError(`${context}.${key} must be a non-negative integer`);
  }
  return value;
}

function list(source: Json, key: string, context: string): unknown[] {
  const value = source[key];
  if (!Array.isArray(value)) throw new DataError(`${context}.${key} must be an array`);
  return value;
}

function parseName(value: unknown, context: string): { en: string; th: string | null } {
  const name = object(value, context);
  return { en: text(name, "en", context), th: optionalText(name, "th", context) };
}

export function parseManifest(input: unknown): TileManifest {
  const root = object(input, "manifest");
  const version = number(root, "version", "manifest");
  if (version !== SUPPORTED_MANIFEST_VERSION) {
    throw new DataError(`unsupported manifest version ${version}`);
  }
  const image = object(root.image, "manifest.image");
  const tiles = object(root.tiles, "manifest.tiles");
  const attribution = object(root.attribution, "manifest.attribution");
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
  if (minLevel > maxLevel) throw new DataError("manifest.tiles.min_level exceeds max_level");
  const width = positiveInteger(image, "width", "manifest.image");
  const height = positiveInteger(image, "height", "manifest.image");
  const top = levels.find((entry) => entry.level === maxLevel);
  if (!top || top.width !== width || top.height !== height) {
    throw new DataError("manifest top level does not match the image dimensions");
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
    },
    attribution: {
      text: text(attribution, "text", "manifest.attribution"),
      url: text(attribution, "url", "manifest.attribution"),
      licence: text(attribution, "licence", "manifest.attribution"),
      provider: text(attribution, "provider", "manifest.attribution"),
    },
    source: {
      dataset: text(source, "dataset", "manifest.source"),
      retrievedAt: optionalText(source, "retrieved_at", "manifest.source"),
    },
  };
}

export function parsePois(input: unknown, manifest: TileManifest): PointOfInterest[] {
  const root = object(input, "pois");
  const seen = new Set<string>();
  return list(root, "pois", "pois").map((entry, index) => {
    const context = `pois[${index}]`;
    const poi = object(entry, context);
    const image = object(poi.image, `${context}.image`);
    const x = number(image, "x", `${context}.image`);
    const y = number(image, "y", `${context}.image`);
    if (x < 0 || y < 0 || x > manifest.image.width || y > manifest.image.height) {
      throw new DataError(`${context}.image lies outside the map image`);
    }
    const id = text(poi, "id", context);
    if (seen.has(id)) throw new DataError(`duplicate POI id '${id}'`);
    seen.add(id);
    const aliases = poi.aliases === undefined ? [] : list(poi, "aliases", context);
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
      image: { x, y },
    };
  });
}

export function parseAreaIndex(input: unknown): AreaSummary[] {
  const root = object(input, "index");
  return list(root, "areas", "index").map((entry, index) => {
    const context = `index.areas[${index}]`;
    const area = object(entry, context);
    return { id: text(area, "id", context), name: parseName(area.name, `${context}.name`) };
  });
}

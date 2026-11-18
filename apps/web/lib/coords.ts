import type { QuadraticFit, TileManifest } from "./manifest";

export interface Point {
  x: number;
  y: number;
}

/**
 * Master-image pixels -> OpenSeadragon viewport coordinates.
 * The viewport spans x in [0, 1] across the image width; y uses the same unit,
 * so the image's bottom edge is at height / width.
 */
export function imageToViewport(point: Point, image: TileManifest["image"]): Point {
  return { x: point.x / image.width, y: point.y / image.width };
}

export function viewportToImage(point: Point, image: TileManifest["image"]): Point {
  return { x: point.x * image.width, y: point.y * image.width };
}

export function tileUrl(
  manifest: TileManifest,
  baseUrl: string,
  level: number,
  column: number,
  row: number,
  template: string = manifest.tiles.urlTemplate,
  version: string = manifest.contentVersion,
): string {
  const path = template
    .replace("{level}", String(level))
    .replace("{column}", String(column))
    .replace("{row}", String(row))
    .replace("{format}", manifest.tiles.format);
  return `${baseUrl.replace(/\/$/, "")}/${path}?v=${encodeURIComponent(version)}`;
}

export function tileSourceOptions(
  manifest: TileManifest,
  baseUrl: string,
  template: string = manifest.tiles.urlTemplate,
  version: string = manifest.contentVersion,
) {
  return {
    width: manifest.image.width,
    height: manifest.image.height,
    tileSize: manifest.tiles.tileSize,
    tileOverlap: manifest.tiles.overlap,
    minLevel: manifest.tiles.minLevel,
    maxLevel: manifest.tiles.maxLevel,
    getTileUrl: (level: number, column: number, row: number) =>
      tileUrl(manifest, baseUrl, level, column, row, template, version),
  };
}

function evaluate(fit: QuadraticFit, a: number, b: number): [number, number] {
  const u = a - fit.origin[0];
  const v = b - fit.origin[1];
  const terms = [1, u, v, u * u, u * v, v * v];
  const sum = (c: number[]) =>
    c.reduce((total, value, index) => total + value * (terms[index] ?? 0), 0);
  return [sum(fit.first), sum(fit.second)];
}

/** WGS84 lon/lat -> master-image pixel at ground level; null outside the area or without a fit. */
export function lonLatToImage(manifest: TileManifest, lon: number, lat: number): Point | null {
  const geographic = manifest.projection.geographic;
  if (!geographic) return null;
  const [x, y] = evaluate(geographic.lonLatToWorld, lon, lat);
  if (x < 0 || y < 0 || x > geographic.widthM || y > geographic.heightM) return null;
  const [a = 0, b = 0, , c = 0] = manifest.projection.worldToImage.px;
  const [d = 0, e = 0, , f = 0] = manifest.projection.worldToImage.py;
  return { x: a * x + b * y + c, y: d * x + e * y + f };
}

/** Master-image pixel -> WGS84 lon/lat of the ground point drawn there. */
export function imageToLonLat(
  manifest: TileManifest,
  point: Point,
): { lon: number; lat: number } | null {
  const geographic = manifest.projection.geographic;
  if (!geographic) return null;
  const [a = 0, b = 0, , c = 0] = manifest.projection.worldToImage.px;
  const [d = 0, e = 0, , f = 0] = manifest.projection.worldToImage.py;
  const determinant = a * e - b * d;
  if (determinant === 0) return null;
  const dx = point.x - c;
  const dy = point.y - f;
  const x = (e * dx - b * dy) / determinant;
  const y = (a * dy - d * dx) / determinant;
  const [lon, lat] = evaluate(geographic.worldToLonLat, x, y);
  return { lon, lat };
}

const LAT_LON = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;

/** "13.7420, 100.5575" (latitude first, as map apps copy it) -> coordinates. */
export function parseLatLon(input: string): { lat: number; lon: number } | null {
  const match = LAT_LON.exec(input);
  if (!match) return null;
  const lat = Number(match[1]);
  const lon = Number(match[2]);
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
}

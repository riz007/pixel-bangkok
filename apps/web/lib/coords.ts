import type { TileManifest } from "./manifest";

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
): string {
  const path = manifest.tiles.urlTemplate
    .replace("{level}", String(level))
    .replace("{column}", String(column))
    .replace("{row}", String(row))
    .replace("{format}", manifest.tiles.format);
  return `${baseUrl.replace(/\/$/, "")}/${path}`;
}

export function tileSourceOptions(manifest: TileManifest, baseUrl: string) {
  return {
    width: manifest.image.width,
    height: manifest.image.height,
    tileSize: manifest.tiles.tileSize,
    tileOverlap: manifest.tiles.overlap,
    minLevel: manifest.tiles.minLevel,
    maxLevel: manifest.tiles.maxLevel,
    getTileUrl: (level: number, column: number, row: number) =>
      tileUrl(manifest, baseUrl, level, column, row),
  };
}

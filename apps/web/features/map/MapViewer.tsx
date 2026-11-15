"use client";

import type OpenSeadragon from "openseadragon";
import { useEffect, useRef, useState } from "react";

import { imageToViewport, tileSourceOptions } from "@/lib/coords";
import type { PointOfInterest, TileManifest } from "@/lib/manifest";

import { categoryInfo } from "./poiCategories";

type ViewerStatus = "loading" | "ready" | "error";

interface MapViewerProps {
  manifest: TileManifest;
  baseUrl: string;
  pois: PointOfInterest[];
  selectedPoiId: string | null;
  onSelectPoi: (id: string) => void;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function MapViewer({ manifest, baseUrl, pois, selectedPoiId, onSelectPoi }: MapViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);
  const markerRefs = useRef(new Map<string, HTMLButtonElement>());
  const [status, setStatus] = useState<ViewerStatus>("loading");
  const [failedTiles, setFailedTiles] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let viewer: OpenSeadragon.Viewer | null = null;
    setStatus("loading");
    setFailedTiles(0);

    import("openseadragon")
      .then(({ default: OSD }) => {
        if (cancelled) return;
        let loadedTiles = 0;
        viewer = OSD({
          element: container,
          tileSources: tileSourceOptions(manifest, baseUrl) as unknown as OpenSeadragon.TileSourceOptions,
          drawer: "canvas",
          imageSmoothingEnabled: false,
          showNavigationControl: false,
          showNavigator: true,
          navigatorPosition: "BOTTOM_RIGHT",
          navigatorSizeRatio: 0.16,
          minZoomImageRatio: 0.7,
          maxZoomPixelRatio: 3,
          visibilityRatio: 0.6,
          constrainDuringPan: true,
          animationTime: prefersReducedMotion() ? 0 : 0.6,
          gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
          gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
        });
        viewerRef.current = viewer;

        const positionMarkers = () => {
          if (!viewer || !viewer.isOpen()) return;
          for (const poi of pois) {
            const marker = markerRefs.current.get(poi.id);
            if (!marker) continue;
            const location = imageToViewport(poi.image, manifest.image);
            const pixel = viewer.viewport.viewportToViewerElementCoordinates(
              new OSD.Point(location.x, location.y),
            );
            marker.style.transform = `translate(${pixel.x}px, ${pixel.y}px)`;
          }
        };

        viewer.addHandler("open", positionMarkers);
        viewer.addHandler("update-viewport", positionMarkers);
        viewer.addHandler("resize", positionMarkers);
        viewer.addHandler("open-failed", () => setStatus("error"));
        viewer.addHandler("tile-loaded", () => {
          loadedTiles += 1;
          setStatus("ready");
        });
        viewer.addHandler("tile-load-failed", () => {
          setFailedTiles((count) => count + 1);
          if (loadedTiles === 0) setStatus("error");
        });
      })
      .catch((error: unknown) => {
        console.error("Failed to start the map viewer", error);
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
      viewerRef.current = null;
      viewer?.destroy();
    };
  }, [manifest, baseUrl, pois]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const poi = pois.find((entry) => entry.id === selectedPoiId);
    if (!viewer || !poi || !viewer.isOpen()) return;
    const location = imageToViewport(poi.image, manifest.image);
    import("openseadragon").then(({ default: OSD }) => {
      viewer.viewport.panTo(new OSD.Point(location.x, location.y), prefersReducedMotion());
    });
  }, [selectedPoiId, pois, manifest]);

  const zoomBy = (factor: number) => {
    const viewport = viewerRef.current?.viewport;
    if (!viewport) return;
    viewport.zoomBy(factor);
    viewport.applyConstraints();
  };

  return (
    <div className="map" data-status={status}>
      <div
        ref={containerRef}
        className="map__canvas"
        role="application"
        aria-label={`Isometric map of ${manifest.name.en}. Use arrow keys to pan and plus or minus to zoom.`}
      />

      <div className="map__markers">
        {pois.map((poi) => {
          const category = categoryInfo(poi.category);
          const selected = poi.id === selectedPoiId;
          return (
            <button
              key={poi.id}
              ref={(element) => {
                if (element) markerRefs.current.set(poi.id, element);
                else markerRefs.current.delete(poi.id);
              }}
              type="button"
              className="marker"
              data-category={poi.category}
              data-poi-id={poi.id}
              aria-pressed={selected}
              aria-label={`${poi.nameEn}, ${category.label}`}
              onClick={() => onSelectPoi(poi.id)}
            >
              <span className="marker__pin" aria-hidden="true">
                {category.glyph}
              </span>
              <span className="marker__label" aria-hidden="true">
                {poi.nameEn}
              </span>
            </button>
          );
        })}
      </div>

      <div className="map__controls" role="group" aria-label="Map controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.5)}>
          <span aria-hidden="true">+</span>
        </button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.5)}>
          <span aria-hidden="true">−</span>
        </button>
        <button
          type="button"
          aria-label="Reset view"
          onClick={() => viewerRef.current?.viewport.goHome()}
        >
          <span aria-hidden="true">⌂</span>
        </button>
      </div>

      {status === "loading" && (
        <p className="map__status" role="status">
          Loading map tiles…
        </p>
      )}
      {status === "error" && (
        <p className="map__status map__status--error" role="alert">
          The map image could not be loaded. Check your connection and reload the page.
        </p>
      )}
      {status === "ready" && failedTiles > 0 && (
        <p className="map__notice" role="status">
          Some map tiles failed to load; parts of the map may be blurry or missing.
        </p>
      )}
    </div>
  );
}

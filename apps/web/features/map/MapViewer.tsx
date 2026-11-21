"use client";

import type OpenSeadragon from "openseadragon";
import {
  type CSSProperties,
  type RefObject,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import {
  imageToViewport,
  type Point,
  tileSourceOptions,
  viewportToImage,
} from "@/lib/coords";
import { type Lang, placeName, STRINGS } from "@/lib/i18n";
import type { PointOfInterest, TileManifest } from "@/lib/manifest";
import { parseMotion } from "@/lib/motion";
import { visibleMarkerIds } from "@/lib/visibility";

import { toggleFullscreen, useFullscreen } from "./fullscreen";
import { PixelIcon } from "./icons";
import { categoryInfo } from "./poiCategories";
import { TrafficLayer } from "./traffic";

/** Bump when motion.json gains data (footways: 2), so cached copies are not reused. */
const MOTION_FORMAT = "m2";

type ViewerStatus = "loading" | "ready" | "error";

const COMPACT_MARKER_ZOOM = 0.35;
const FOCUS_IMAGE_ZOOM = 0.6;

export interface MapCommands {
  zoomBy: (factor: number) => void;
  home: () => void;
  center: () => Point | null;
  goTo: (point: Point) => void;
}

interface MapViewerProps {
  manifest: TileManifest;
  baseUrl: string;
  pois: PointOfInterest[];
  selectedPoiId: string | null;
  onSelectPoi: (id: string) => void;
  playing: boolean;
  showLabels: boolean;
  lang: Lang;
  tourNumbers: Map<string, number>;
  /** When set, only these places get pins (category filter); null shows all. */
  visibleIds?: Set<string> | null;
  commandsRef: RefObject<MapCommands | null>;
  onAnimationAvailable: (available: boolean) => void;
  pin: Point | null;
}

/** Clockwise screen angle of world north, from the published world -> image matrix. */
function northDegrees(manifest: TileManifest): number {
  const { px, py } = manifest.projection.worldToImage;
  return (Math.atan2(px[1] ?? 0, -(py[1] ?? 0)) * 180) / Math.PI;
}

const TILE_RETRIES = 3;
const TILE_RETRY_DELAY_MS = 1200;

/** OpenSeadragon reports cancelled downloads (panning, layer swaps) as failures with exactly
 * this message; real errors read "...aborted or errored out" or mention a timeout. */
const CANCELLED = "Image load aborted.";

function isRealFailure(event: {
  message?: string;
  maxReached?: boolean;
}): boolean {
  if (event.maxReached === false) return false;
  return event.message !== CANCELLED;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

async function loadMotion(url: string) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} responded with ${response.status}`);
  return parseMotion(await response.json());
}

export function MapViewer({
  manifest,
  baseUrl,
  pois,
  selectedPoiId,
  onSelectPoi,
  playing,
  showLabels,
  lang,
  tourNumbers,
  visibleIds = null,
  commandsRef,
  onAnimationAvailable,
  pin,
}: MapViewerProps) {
  const text = STRINGS[lang];
  const fullscreen = useFullscreen();
  const pinRef = useRef<HTMLDivElement>(null);
  const pinPointRef = useRef(pin);
  const positionRef = useRef<(() => void) | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);
  const markerRefs = useRef(new Map<string, HTMLButtonElement>());
  const animationRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const trafficRef = useRef<TrafficLayer | null>(null);
  const upperRef = useRef<HTMLCanvasElement>(null);
  const frontRef = useRef<HTMLDivElement>(null);
  const navigatorId = `map-navigator-${useId().replace(/:/g, "")}`;
  const [status, setStatus] = useState<ViewerStatus>("loading");
  const [failedTiles, setFailedTiles] = useState(0);
  const [noticeDismissed, setNoticeDismissed] = useState(false);
  const playingRef = useRef(playing);
  const selectedRef = useRef(selectedPoiId);
  const tourRef = useRef(tourNumbers);
  const availableRef = useRef(onAnimationAvailable);
  const focusRef = useRef<((id: string) => void) | null>(null);

  useEffect(() => {
    availableRef.current = onAnimationAvailable;
    tourRef.current = tourNumbers;
  }, [onAnimationAvailable, tourNumbers]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let viewer: OpenSeadragon.Viewer | null = null;
    let overlay: OpenSeadragon.Viewer | null = null;
    let front: OpenSeadragon.Viewer | null = null;
    let navigatorObserver: ResizeObserver | null = null;
    setStatus("loading");
    setFailedTiles(0);
    availableRef.current(false);

    import("openseadragon")
      .then(({ default: OSD }) => {
        if (cancelled) return;
        let loadedTiles = 0;
        viewer = OSD({
          element: container,
          tileSources: tileSourceOptions(
            manifest,
            baseUrl,
            manifest.tiles.urlTemplate,
            manifest.contentVersion,
          ) as unknown as OpenSeadragon.TileSourceOptions,
          drawer: "canvas",
          imageSmoothingEnabled: false,
          showNavigationControl: false,
          showNavigator: true,
          navigatorId,
          navigatorSizeRatio: 0.16,
          minZoomImageRatio: 0.7,
          maxZoomPixelRatio: 8,
          minPixelRatio: 1,
          smoothTileEdgesMinZoom: Infinity,
          maxImageCacheCount: 1500,
          imageLoaderLimit: 8,
          tileRetryMax: TILE_RETRIES,
          tileRetryDelay: TILE_RETRY_DELAY_MS,
          visibilityRatio: 0.6,
          constrainDuringPan: true,
          animationTime: prefersReducedMotion() ? 0 : 0.6,
          gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
          gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
        });
        viewerRef.current = viewer;
        const current = viewer;
        commandsRef.current = {
          zoomBy: (factor) => {
            current.viewport.zoomBy(factor);
            current.viewport.applyConstraints();
          },
          home: () => current.viewport.goHome(),
          center: () =>
            current.isOpen()
              ? viewportToImage(
                  current.viewport.getCenter(true),
                  manifest.image,
                )
              : null,
          goTo: (point) => goToImage(point),
        };

        const positionMarkers = () => {
          if (!current.isOpen()) return;
          const imageZoom = current.viewport.viewportToImageZoom(
            current.viewport.getZoom(true),
          );
          container.parentElement?.setAttribute(
            "data-detail",
            imageZoom < COMPACT_MARKER_ZOOM ? "compact" : "full",
          );
          const shown = visibleMarkerIds(pois, imageZoom, selectedRef.current);
          for (const id of tourRef.current.keys()) shown.add(id);
          for (const poi of pois) {
            const marker = markerRefs.current.get(poi.id);
            if (!marker) continue;
            marker.hidden = !shown.has(poi.id);
            if (marker.hidden) continue;
            const location = imageToViewport(poi.image, manifest.image);
            const pixel = current.viewport.viewportToViewerElementCoordinates(
              new OSD.Point(location.x, location.y),
            );
            marker.style.transform = `translate(${pixel.x}px, ${pixel.y}px)`;
          }
          const pinElement = pinRef.current;
          const pinPoint = pinPointRef.current;
          if (pinElement && pinPoint) {
            const location = imageToViewport(pinPoint, manifest.image);
            const pixel = current.viewport.viewportToViewerElementCoordinates(
              new OSD.Point(location.x, location.y),
            );
            pinElement.style.transform = `translate(${pixel.x}px, ${pixel.y}px)`;
          }
        };
        positionRef.current = positionMarkers;

        const goToImage = (point: Point) => {
          if (!current.isOpen()) return;
          const location = imageToViewport(point, manifest.image);
          const viewport = current.viewport;
          const zoom = Math.max(
            viewport.getZoom(),
            viewport.imageToViewportZoom(FOCUS_IMAGE_ZOOM),
          );
          const bounds = viewport.getBounds();
          const width = 1 / zoom;
          const height = width * (bounds.height / bounds.width);
          viewport.fitBounds(
            new OSD.Rect(
              location.x - width / 2,
              location.y - height / 2,
              width,
              height,
            ),
            prefersReducedMotion(),
          );
        };
        focusRef.current = (id) => {
          const poi = pois.find((entry) => entry.id === id);
          if (poi) goToImage(poi.image);
        };
        current.addHandler("open", () => {
          if (selectedRef.current) focusRef.current?.(selectedRef.current);
        });
        current.addHandler("open", positionMarkers);
        current.addHandler("update-viewport", positionMarkers);
        const followers: OpenSeadragon.Viewer[] = [];
        let smoothing: boolean | null = null;
        const updateSmoothing = () => {
          if (!current.isOpen()) return;
          const imageZoom = current.viewport.viewportToImageZoom(
            current.viewport.getZoom(true),
          );
          const wanted = imageZoom < 1;
          if (wanted === smoothing) return;
          smoothing = wanted;
          for (const target of [current, ...followers]) {
            target.drawer.setImageSmoothingEnabled(wanted);
          }
        };
        current.addHandler("update-viewport", updateSmoothing);
        current.addHandler("resize", positionMarkers);
        const navigatorElement = document.getElementById(navigatorId);
        if (navigatorElement && typeof ResizeObserver !== "undefined") {
          navigatorObserver = new ResizeObserver(() =>
            current.navigator?.updateSize(),
          );
          navigatorObserver.observe(navigatorElement);
        }
        current.addHandler("open-failed", () => setStatus("error"));
        current.addHandler("tile-loaded", () => {
          loadedTiles += 1;
          setStatus("ready");
        });
        current.addHandler("tile-load-failed", (event) => {
          if (!isRealFailure(event)) return;
          setFailedTiles((count) => count + 1);
          if (loadedTiles === 0) setStatus("error");
        });

        const animation = manifest.animation;
        const canvas = animationRef.current;
        const overlayContainer = overlayRef.current;
        if (!animation?.motionUrl || !canvas || !overlayContainer) return;
        const follow = (element: HTMLElement, template: string) => {
          const follower: OpenSeadragon.Viewer = OSD({
            element,
            tileSources: tileSourceOptions(
              manifest,
              baseUrl,
              template,
              manifest.contentVersion,
            ) as unknown as OpenSeadragon.TileSourceOptions,
            drawer: "canvas",
            imageSmoothingEnabled: false,
            showNavigationControl: false,
            mouseNavEnabled: false,
            minZoomImageRatio: 0,
            maxZoomPixelRatio: 1000,
            minPixelRatio: 1,
            smoothTileEdgesMinZoom: Infinity,
            maxImageCacheCount: 1500,
            imageLoaderLimit: 4,
            tileRetryMax: TILE_RETRIES,
            tileRetryDelay: TILE_RETRY_DELAY_MS,
            visibilityRatio: 0,
            constrainDuringPan: false,
            animationTime: 0,
          });
          const sync = () => {
            if (!follower.isOpen()) return;
            follower.viewport.zoomTo(
              current.viewport.getZoom(true),
              undefined,
              true,
            );
            follower.viewport.panTo(current.viewport.getCenter(true), true);
          };
          current.addHandler("viewport-change", sync);
          current.addHandler("resize", sync);
          follower.addHandler("open", sync);
          follower.addHandler("resize", sync);
          followers.push(follower);
          smoothing = null;
          return follower;
        };
        const template = animation.overlayUrlTemplate ?? null;
        if (template) {
          overlay = follow(overlayContainer, template);
        }
        const frontTemplateValue = animation.frontUrlTemplate ?? null;
        if (frontTemplateValue && frontRef.current) {
          front = follow(frontRef.current, frontTemplateValue);
        }
        loadMotion(
          `${baseUrl}/${animation.motionUrl}?v=${manifest.contentVersion}-${MOTION_FORMAT}`,
        )
          .then((motion) => {
            if (cancelled) return;
            const traffic = new TrafficLayer(
              canvas,
              current,
              OSD,
              manifest,
              motion,
              playingRef.current,
              motion.rail.length > 0 ? upperRef.current : null,
            );
            trafficRef.current = traffic;
            traffic.start();
            canvas.dataset.vehicles = String(traffic.vehicleCount);
            canvas.dataset.people = String(traffic.peopleCount);
            availableRef.current(true);
          })
          .catch((error: unknown) =>
            console.warn("Animation unavailable", error),
          );
      })
      .catch((error: unknown) => {
        console.error("Failed to start the map viewer", error);
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
      viewerRef.current = null;
      commandsRef.current = null;
      focusRef.current = null;
      trafficRef.current?.destroy();
      trafficRef.current = null;
      overlay?.destroy();
      front?.destroy();
      navigatorObserver?.disconnect();
      viewer?.destroy();
    };
  }, [manifest, baseUrl, pois, navigatorId, commandsRef]);

  useEffect(() => {
    playingRef.current = playing;
    trafficRef.current?.setPlaying(playing);
  }, [playing]);

  useEffect(() => {
    pinPointRef.current = pin;
    positionRef.current?.();
  }, [pin]);

  useEffect(() => {
    selectedRef.current = selectedPoiId;
    if (selectedPoiId) focusRef.current?.(selectedPoiId);
  }, [selectedPoiId]);

  return (
    <div
      className="map"
      data-status={status}
      data-labels={showLabels ? "on" : "off"}
    >
      <div
        ref={containerRef}
        className="map__canvas"
        role="application"
        aria-label={
          lang === "th"
            ? `แผนที่ไอโซเมตริกของ${manifest.name.th ?? manifest.name.en} ใช้ปุ่มลูกศรเพื่อเลื่อน และปุ่มบวกลบเพื่อซูม`
            : `Isometric map of ${manifest.name.en}. Use arrow keys to pan and plus or minus to zoom.`
        }
      />

      <canvas
        ref={animationRef}
        className="map__animation"
        aria-hidden="true"
      />
      <div ref={overlayRef} className="map__overlay" aria-hidden="true" />
      <canvas
        ref={upperRef}
        className="map__animation map__animation--upper"
        aria-hidden="true"
      />
      <div
        ref={frontRef}
        className="map__overlay map__overlay--front"
        aria-hidden="true"
      />

      <div className="map__markers">
        {(visibleIds ? pois.filter((poi) => visibleIds.has(poi.id)) : pois).map(
          (poi) => {
            const category = categoryInfo(poi.category);
            const selected = poi.id === selectedPoiId;
            const number = tourNumbers.get(poi.id);
            const names = placeName(poi, lang);
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
                data-tour={number !== undefined ? "yes" : "no"}
                aria-pressed={selected}
                aria-label={`${number !== undefined ? `${number}. ` : ""}${names.primary}, ${category.label}`}
                onClick={() => onSelectPoi(poi.id)}
              >
                <span className="marker__pin" aria-hidden="true">
                  {number ?? category.glyph}
                </span>
                <span className="marker__label" aria-hidden="true">
                  {names.primary}
                </span>
              </button>
            );
          },
        )}
      </div>

      <div ref={pinRef} className="map__pin" hidden={!pin}>
        <span role="img" aria-label={text.searchedLocation} />
      </div>

      <div id={navigatorId} className="map__navigator" aria-hidden="true" />
      <div
        className="map__compass"
        role="img"
        aria-label={text.northArrow}
        style={{ "--north": `${northDegrees(manifest)}deg` } as CSSProperties}
      >
        <span className="map__compass-arrow" aria-hidden="true">
          ▲
        </span>
        <span aria-hidden="true">{lang === "th" ? "เหนือ" : "N"}</span>
      </div>

      <div className="map__zoom" role="group" aria-label={text.zoomGroup}>
        <button
          type="button"
          aria-label={text.zoomIn}
          onClick={() => commandsRef.current?.zoomBy(1.5)}
        >
          <span aria-hidden="true">+</span>
        </button>
        <button
          type="button"
          aria-label={text.zoomOut}
          onClick={() => commandsRef.current?.zoomBy(1 / 1.5)}
        >
          <span aria-hidden="true">−</span>
        </button>
        <button
          type="button"
          aria-label={text.home}
          onClick={() => commandsRef.current?.home()}
        >
          <span aria-hidden="true">⌂</span>
        </button>
        {fullscreen.available && (
          <button
            type="button"
            aria-label={
              fullscreen.active ? text.exitFullscreen : text.fullscreen
            }
            aria-pressed={fullscreen.active}
            onClick={toggleFullscreen}
          >
            <PixelIcon name={fullscreen.active ? "shrink" : "expand"} />
          </button>
        )}
      </div>

      {status === "loading" && (
        <p className="map__status" role="status">
          {text.loadingTiles}
        </p>
      )}
      {status === "error" && (
        <p className="map__status map__status--error" role="alert">
          {text.mapUnavailable}. {text.mapUnavailableHint}
        </p>
      )}
      {status === "ready" && failedTiles > 0 && !noticeDismissed && (
        <p className="map__notice" role="status">
          {text.tilesFailed}
          <button
            type="button"
            className="map__notice-close"
            aria-label={text.dismiss}
            onClick={() => setNoticeDismissed(true)}
          >
            <span aria-hidden="true">×</span>
          </button>
        </p>
      )}
    </div>
  );
}

import type OpenSeadragon from "openseadragon";

import type { TileManifest } from "@/lib/manifest";
import {
  advance,
  laneOffset,
  type Matrix,
  type MotionData,
  Network,
  seededRandom,
  spawn,
  type SpawnRule,
  type Vehicle,
  type VehicleType,
  worldToImage,
} from "@/lib/motion";

const MIN_IMAGE_ZOOM = 0.3;
const PIXEL_ART_ZOOM = 1;
const MAX_STEP_SECONDS = 0.1;
const MAX_VEHICLES = 15000;
const MAX_PEOPLE = 8000;
/** People are about 2 px wide at 1:1, so they are drawn only from this zoom in. */
const PEOPLE_MIN_ZOOM = 0.75;
const SEED = 20261117;
const WAKE_COLOUR = "rgba(196, 222, 210, 0.75)";
const GLASS = "#33434f";
const LIGHT = { x: -0.94, y: -0.34 };

const CAR: VehicleType = {
  name: "car",
  layer: "roads",
  lengthM: 4.4,
  widthM: 1.8,
  heightM: 0.8,
  speedMps: 9,
  body: ["#f2f2ee", "#c9ccd1", "#2f3237", "#b8323a", "#2c5d9b", "#d9d4c4"],
  roof: "#d6dce0",
  cabin: { lengthFraction: 0.5, heightM: 0.6, colour: GLASS },
  laneFraction: 0.5,
};
const TAXI: VehicleType = {
  ...CAR,
  name: "taxi",
  body: ["#e5629e", "#c7d93b", "#e5629e", "#e8892b"],
};
const TUK_TUK: VehicleType = {
  name: "tuk-tuk",
  layer: "roads",
  lengthM: 2.8,
  widthM: 1.4,
  heightM: 0.7,
  speedMps: 7,
  body: ["#1f6fb2", "#2b8a4b", "#c0392b"],
  roof: "#f2c94c",
  cabin: { lengthFraction: 0.75, heightM: 0.9, colour: "#f2c94c" },
  laneFraction: 0.55,
};
const BUS: VehicleType = {
  name: "bus",
  layer: "roads",
  lengthM: 11,
  widthM: 2.5,
  heightM: 3,
  speedMps: 7,
  body: ["#c8352e", "#e9dfc6", "#2c6fa8"],
  roof: "#efe9dc",
  laneFraction: 0.5,
};
const MOTORBIKE: VehicleType = {
  name: "motorbike",
  layer: "roads",
  lengthM: 1.9,
  widthM: 0.7,
  heightM: 1.1,
  speedMps: 10,
  body: ["#26282c", "#8a1c1c", "#2d4f7c"],
  roof: "#3b3e44",
  laneFraction: 0.8,
};
const EXPRESS_BOAT: VehicleType = {
  name: "express boat",
  layer: "waterways",
  lengthM: 24,
  widthM: 4,
  heightM: 0.7,
  speedMps: 7,
  body: ["#f4efe2"],
  roof: "#e07a2e",
  cabin: { lengthFraction: 0.65, heightM: 1.3, colour: "#e07a2e" },
  laneFraction: 0.35,
  wake: true,
};
const LONGTAIL: VehicleType = {
  name: "long-tail boat",
  layer: "waterways",
  lengthM: 11,
  widthM: 1.8,
  heightM: 0.5,
  speedMps: 9,
  body: ["#7a5432", "#5b3f27"],
  roof: "#3d6fa8",
  cabin: { lengthFraction: 0.45, heightM: 0.9, colour: "#3d6fa8" },
  laneFraction: 0.25,
  wake: true,
};
const FERRY: VehicleType = {
  name: "ferry",
  layer: "waterways",
  lengthM: 14,
  widthM: 5,
  heightM: 0.8,
  speedMps: 3,
  body: ["#e9eef2"],
  roof: "#2f6f9f",
  cabin: { lengthFraction: 0.6, heightM: 1.5, colour: "#2f6f9f" },
  laneFraction: 0,
  wake: true,
};

const METRO: VehicleType = {
  name: "metro train",
  layer: "rail",
  lengthM: 20,
  widthM: 3.1,
  heightM: 3.4,
  speedMps: 12,
  body: ["#9aa3ab"],
  roof: "#e4e7ea",
  laneFraction: 0.5,
  cars: 4,
};
const MAINLINE: VehicleType = {
  name: "train",
  layer: "rail",
  lengthM: 20,
  widthM: 2.9,
  heightM: 3.6,
  speedMps: 11,
  body: ["#c8352e", "#2c5d9b"],
  roof: "#d9d4c4",
  laneFraction: 0.5,
  cars: 6,
};
const PERSON: VehicleType = {
  name: "person",
  layer: "footways",
  lengthM: 0.36,
  widthM: 0.5,
  heightM: 0.85,
  speedMps: 1.3,
  body: ["#f4f1ea", "#9ec3e6", "#f2c94c", "#c0392b", "#2c3e66", "#e58fb0", "#3e8e5e", "#8a8f96"],
  roof: "#2a2224",
  laneFraction: 0.8,
  walker: true,
};
const SIDEWALK_PERSON: VehicleType = { ...PERSON, layer: "roads" };
const PERSON_LEGS = ["#2c3140", "#1e1f24", "#4a5f86", "#8b7a5c", "#3b3b3f"];
const PERSON_SKIN = ["#c98d62", "#a86f4a", "#e0ac82", "#8c5a3a"];
const PERSON_HAIR = "#241c1e";
const TORSO_M = 0.6;
const HEAD_M = 0.27;
const FOOT_RULES: SpawnRule[] = [
  { type: PERSON, kinds: ["pedestrian"], metresPerVehicle: 5 },
  { type: PERSON, kinds: ["footway"], metresPerVehicle: 12 },
  { type: PERSON, kinds: ["steps"], metresPerVehicle: 15 },
  { type: PERSON, kinds: ["path"], metresPerVehicle: 30 },
];
const SIDEWALK_RULES: SpawnRule[] = [
  { type: SIDEWALK_PERSON, kinds: ["major"], metresPerVehicle: 40 },
  { type: SIDEWALK_PERSON, kinds: ["minor"], metresPerVehicle: 70 },
];

const RAIL_RULES: SpawnRule[] = [
  { type: METRO, kinds: ["metro"], metresPerVehicle: 1200 },
  { type: MAINLINE, kinds: ["rail"], metresPerVehicle: 3000 },
];
const CAR_GAP_M = 0.8;
const ELEVATED_M = 0.5;

const ROAD_RULES: SpawnRule[] = [
  { type: CAR, kinds: ["major"], metresPerVehicle: 40 },
  { type: CAR, kinds: ["minor"], metresPerVehicle: 140 },
  { type: CAR, kinds: ["service"], metresPerVehicle: 400 },
  { type: TAXI, kinds: ["major"], metresPerVehicle: 110 },
  { type: TAXI, kinds: ["minor"], metresPerVehicle: 400 },
  { type: TUK_TUK, kinds: ["major", "minor"], metresPerVehicle: 300 },
  { type: BUS, kinds: ["major"], metresPerVehicle: 450 },
  { type: MOTORBIKE, kinds: ["major"], metresPerVehicle: 60 },
  { type: MOTORBIKE, kinds: ["minor"], metresPerVehicle: 160 },
];
const WATER_RULES: SpawnRule[] = [
  { type: EXPRESS_BOAT, kinds: ["river"], metresPerVehicle: 500 },
  { type: LONGTAIL, kinds: ["river"], metresPerVehicle: 350 },
  { type: LONGTAIL, kinds: ["canal"], metresPerVehicle: 500 },
  { type: FERRY, kinds: ["ferry"], metresPerVehicle: 1200 },
];

const shades = new Map<string, string>();

function shade(colour: string, factor: number): string {
  const key = `${colour}:${factor.toFixed(2)}`;
  const cached = shades.get(key);
  if (cached) return cached;
  const value = Number.parseInt(colour.slice(1), 16);
  const channel = (offset: number) => Math.round(((value >> offset) & 255) * factor);
  const result = `rgb(${channel(16)}, ${channel(8)}, ${channel(0)})`;
  shades.set(key, result);
  return result;
}

interface Box {
  cx: number;
  cy: number;
  hx: number;
  hy: number;
  halfLength: number;
  halfWidth: number;
  z0: number;
  z1: number;
}

export class TrafficLayer {
  private readonly roads: Network;
  private readonly water: Network;
  private readonly rail: Network;
  private readonly foot: Network;
  private readonly vehicles: Vehicle[];
  private readonly people: number;
  private showPeople = false;
  private readonly random = seededRandom(SEED + 1);
  private readonly matrix: Matrix;
  private readonly towardCamera: { x: number; y: number };
  private readonly offscreen: HTMLCanvasElement;
  private frame = 0;
  private last = 0;
  private playing: boolean;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly viewer: OpenSeadragon.Viewer,
    private readonly osd: typeof OpenSeadragon,
    manifest: TileManifest,
    motion: MotionData,
    playing: boolean,
    private readonly upper: HTMLCanvasElement | null = null,
  ) {
    this.roads = new Network(motion.roads);
    this.water = new Network(motion.waterways);
    this.rail = new Network(motion.rail);
    this.foot = new Network(motion.footways);
    const walkers = [
      ...spawn(this.foot, FOOT_RULES, SEED + 4, MAX_PEOPLE),
      ...(motion.sidewalkM > 0
        ? spawn(this.roads, SIDEWALK_RULES, SEED + 5, MAX_PEOPLE / 2, motion.sidewalkM)
        : []),
    ];
    this.people = walkers.length;
    this.vehicles = [
      ...spawn(this.roads, ROAD_RULES, SEED, MAX_VEHICLES),
      ...spawn(this.water, WATER_RULES, SEED + 2, MAX_VEHICLES),
      ...spawn(this.rail, RAIL_RULES, SEED + 3, MAX_VEHICLES),
      ...walkers,
    ];
    this.matrix = manifest.projection.worldToImage;
    const azimuth = (manifest.projection.cameraAzimuthDeg * Math.PI) / 180;
    this.towardCamera = { x: -Math.sin(azimuth), y: -Math.cos(azimuth) };
    this.offscreen = document.createElement("canvas");
    this.playing = playing;
  }

  get vehicleCount(): number {
    return this.vehicles.length - this.people;
  }

  get peopleCount(): number {
    return this.people;
  }

  setPlaying(playing: boolean) {
    this.playing = playing;
  }

  start() {
    const tick = (time: number) => {
      const seconds = this.last ? Math.min((time - this.last) / 1000, MAX_STEP_SECONDS) : 0;
      this.last = time;
      if (this.playing && seconds > 0) {
        for (const vehicle of this.vehicles) {
          advance(this.network(vehicle), vehicle, seconds, this.random);
        }
      }
      this.draw();
      this.frame = requestAnimationFrame(tick);
    };
    this.frame = requestAnimationFrame(tick);
  }

  destroy() {
    cancelAnimationFrame(this.frame);
  }

  private network(vehicle: Vehicle): Network {
    const layer = vehicle.type.layer;
    if (layer === "footways") return this.foot;
    return layer === "roads" ? this.roads : layer === "rail" ? this.rail : this.water;
  }

  private draw() {
    this.drawCanvas(this.canvas, this.upper ? false : null);
    if (this.upper) this.drawCanvas(this.upper, true);
  }

  /** `elevated`: true draws only vehicles on viaducts, false only those at grade, null all. */
  private drawCanvas(canvas: HTMLCanvasElement, elevated: boolean | null) {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.round(canvas.clientWidth * ratio);
    const height = Math.round(canvas.clientHeight * ratio);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, width, height);
    const item = this.viewer.world.getItemAt(0);
    if (!item || !this.viewer.isOpen()) return;
    const imageZoom = item.viewportToImageZoom(this.viewer.viewport.getZoom(true));
    if (imageZoom < MIN_IMAGE_ZOOM) return;
    this.showPeople = imageZoom >= PEOPLE_MIN_ZOOM;
    const visible = item.viewportToImageRectangle(this.viewer.viewport.getBounds(true));
    const left = Math.floor(visible.x) - 8;
    const top = Math.floor(visible.y) - 8;
    const right = Math.ceil(visible.x + visible.width) + 8;
    const bottom = Math.ceil(visible.y + visible.height) + 8;
    const origin = item.imageToViewerElementCoordinates(new this.osd.Point(left, top));
    const scale = imageZoom * ratio;

    if (imageZoom >= PIXEL_ART_ZOOM) {
      const off = this.offscreen;
      if (off.width !== right - left || off.height !== bottom - top) {
        off.width = right - left;
        off.height = bottom - top;
      }
      const offContext = off.getContext("2d");
      if (!offContext) return;
      offContext.setTransform(1, 0, 0, 1, 0, 0);
      offContext.clearRect(0, 0, off.width, off.height);
      offContext.translate(-left, -top);
      this.drawVehicles(offContext, left, top, right, bottom, elevated);
      context.imageSmoothingEnabled = false;
      context.drawImage(off, origin.x * ratio, origin.y * ratio, off.width * scale, off.height * scale);
    } else {
      context.setTransform(scale, 0, 0, scale, origin.x * ratio - left * scale, origin.y * ratio - top * scale);
      this.drawVehicles(context, left, top, right, bottom, elevated);
      context.setTransform(1, 0, 0, 1, 0, 0);
    }
  }

  private drawVehicles(
    context: CanvasRenderingContext2D,
    left: number,
    top: number,
    right: number,
    bottom: number,
    elevated: boolean | null,
  ) {
    const margin = 60;
    const ordered: { depth: number; box: Box; vehicle: Vehicle; index: number }[] = [];
    for (let index = 0; index < this.vehicles.length; index += 1) {
      const vehicle = this.vehicles[index]!;
      if (vehicle.type.walker && (!this.showPeople || elevated === true)) continue;
      const network = this.network(vehicle);
      const cars = vehicle.type.cars ?? 1;
      for (let car = 0; car < cars; car += 1) {
        const distance = vehicle.distance - car * (vehicle.type.lengthM + CAR_GAP_M);
        const point = network.pointAt(vehicle.path, distance, vehicle.forward);
        if (elevated !== null && point.z > ELEVATED_M !== elevated) continue;
        const offset = laneOffset(point, vehicle.lateralM);
        const cx = point.x + offset.dx;
        const cy = point.y + offset.dy;
        const [ix, iy] = worldToImage(this.matrix, cx, cy, point.z);
        if (ix < left - margin || ix > right + margin || iy < top - margin || iy > bottom + margin) {
          continue;
        }
        ordered.push({
          depth: worldToImage(this.matrix, cx, cy, 0)[1],
          vehicle,
          index,
          box: {
            cx,
            cy,
            hx: point.hx,
            hy: point.hy,
            halfLength: vehicle.type.lengthM / 2,
            halfWidth: vehicle.type.widthM / 2,
            z0: point.z,
            z1: point.z + vehicle.type.heightM,
          },
        });
      }
    }
    ordered.sort((a, b) => a.depth - b.depth);
    for (const { vehicle, box, index } of ordered) {
      const type = vehicle.type;
      if (type.walker) {
        this.drawPerson(context, box, vehicle.colour, index);
        continue;
      }
      if (type.wake) this.drawWake(context, box);
      this.drawBox(context, box, vehicle.colour, type.cabin ? vehicle.colour : type.roof);
      if (type.cabin) {
        const cabin: Box = {
          ...box,
          cx: box.cx - box.hx * box.halfLength * (1 - type.cabin.lengthFraction) * 0.4,
          cy: box.cy - box.hy * box.halfLength * (1 - type.cabin.lengthFraction) * 0.4,
          halfLength: box.halfLength * type.cabin.lengthFraction,
          halfWidth: box.halfWidth * 0.85,
          z0: box.z1,
          z1: box.z1 + type.cabin.heightM,
        };
        this.drawBox(context, cabin, type.cabin.colour, type.roof);
      }
    }
  }

  /** Legs, shirt and head as three stacked boxes: about 2 x 5 px at 1:1. */
  private drawPerson(context: CanvasRenderingContext2D, box: Box, shirt: string, index: number) {
    const legs = PERSON_LEGS[index % PERSON_LEGS.length]!;
    const skin = PERSON_SKIN[Math.floor(index / PERSON_LEGS.length) % PERSON_SKIN.length]!;
    this.drawBox(context, box, legs, legs);
    const torso: Box = { ...box, z0: box.z1, z1: box.z1 + TORSO_M };
    this.drawBox(context, torso, shirt, shirt);
    const head: Box = {
      ...box,
      halfLength: box.halfLength * 0.75,
      halfWidth: box.halfWidth * 0.55,
      z0: torso.z1,
      z1: torso.z1 + HEAD_M,
    };
    this.drawBox(context, head, skin, PERSON_HAIR);
  }

  private corners(box: Box): [number, number][] {
    const lx = -box.hy;
    const ly = box.hx;
    const { cx, cy, hx, hy, halfLength: l, halfWidth: w } = box;
    return [
      [cx + hx * l + lx * w, cy + hy * l + ly * w],
      [cx - hx * l + lx * w, cy - hy * l + ly * w],
      [cx - hx * l - lx * w, cy - hy * l - ly * w],
      [cx + hx * l - lx * w, cy + hy * l - ly * w],
    ];
  }

  private drawBox(context: CanvasRenderingContext2D, box: Box, sides: string, top: string) {
    const corners = this.corners(box);
    const project = (x: number, y: number, z: number) => worldToImage(this.matrix, x, y, z);
    for (let index = 0; index < 4; index += 1) {
      const [ax, ay] = corners[index]!;
      const [bx, by] = corners[(index + 1) % 4]!;
      const nx = (ax + bx) / 2 - box.cx;
      const ny = (ay + by) / 2 - box.cy;
      const length = Math.hypot(nx, ny) || 1;
      if ((nx * this.towardCamera.x + ny * this.towardCamera.y) / length <= 0) continue;
      const lit = (nx * LIGHT.x + ny * LIGHT.y) / length;
      context.fillStyle = shade(sides, lit > 0 ? 0.92 : 0.7);
      context.beginPath();
      const quad = [project(ax, ay, box.z0), project(bx, by, box.z0), project(bx, by, box.z1), project(ax, ay, box.z1)];
      context.moveTo(quad[0]![0], quad[0]![1]);
      for (const [x, y] of quad.slice(1)) context.lineTo(x, y);
      context.closePath();
      context.fill();
    }
    context.fillStyle = top;
    context.beginPath();
    corners.forEach(([x, y], index) => {
      const [px, py] = project(x, y, box.z1);
      if (index === 0) context.moveTo(px, py);
      else context.lineTo(px, py);
    });
    context.closePath();
    context.fill();
  }

  private drawWake(context: CanvasRenderingContext2D, box: Box) {
    const lx = -box.hy;
    const ly = box.hx;
    const sternX = box.cx - box.hx * box.halfLength;
    const sternY = box.cy - box.hy * box.halfLength;
    const trail = box.halfLength * 1.4;
    context.strokeStyle = WAKE_COLOUR;
    context.lineWidth = 1;
    context.beginPath();
    for (const side of [-1, 1]) {
      const [x0, y0] = worldToImage(this.matrix, sternX + lx * box.halfWidth * side * 0.6, sternY + ly * box.halfWidth * side * 0.6, 0);
      const [x1, y1] = worldToImage(
        this.matrix,
        sternX - box.hx * trail + lx * box.halfWidth * side * 2.5,
        sternY - box.hy * trail + ly * box.halfWidth * side * 2.5,
        0,
      );
      context.moveTo(x0, y0);
      context.lineTo(x1, y1);
    }
    context.stroke();
  }
}

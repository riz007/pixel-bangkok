import { DataError } from "./manifest.ts";

export interface MotionPath {
  id: string;
  kind: string;
  start: number;
  end: number;
  points: [number, number][];
  z: number[] | null;
  oneway: -1 | 0 | 1;
  widthM: number;
  colour: string | null;
}

export interface MotionData {
  nodeCount: number;
  roads: MotionPath[];
  waterways: MotionPath[];
  rail: MotionPath[];
}

export interface VehicleType {
  name: string;
  layer: "roads" | "waterways" | "rail";
  lengthM: number;
  widthM: number;
  heightM: number;
  speedMps: number;
  body: string[];
  roof: string;
  cabin?: { lengthFraction: number; heightM: number; colour: string };
  laneFraction: number;
  wake?: boolean;
  cars?: number;
}

export interface Vehicle {
  type: VehicleType;
  colour: string;
  path: number;
  forward: boolean;
  distance: number;
  lateralM: number;
  speedMps: number;
}

type Json = Record<string, unknown>;

function isRecord(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parsePath(value: unknown, context: string, nodeCount: number): MotionPath {
  if (!isRecord(value)) throw new DataError(`${context} must be an object`);
  const points = value.points;
  if (
    !Array.isArray(points) ||
    points.length < 2 ||
    !points.every(
      (point) =>
        Array.isArray(point) &&
        (point.length === 2 || point.length === 3) &&
        point.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate)),
    )
  ) {
    throw new DataError(`${context}.points must be at least two [x, y] or [x, y, z] points`);
  }
  const rows = points as number[][];
  const hasZ = rows.every((point) => point.length === 3);
  const start = value.start;
  const end = value.end;
  if (
    typeof start !== "number" ||
    typeof end !== "number" ||
    start < 0 ||
    end < 0 ||
    start >= nodeCount ||
    end >= nodeCount
  ) {
    throw new DataError(`${context} has invalid start/end nodes`);
  }
  const oneway = value.oneway === 1 || value.oneway === -1 ? value.oneway : 0;
  return {
    id: typeof value.id === "string" ? value.id : context,
    kind: typeof value.kind === "string" ? value.kind : "minor",
    start,
    end,
    points: rows.map((point) => [point[0]!, point[1]!]),
    z: hasZ ? rows.map((point) => point[2]!) : null,
    oneway,
    widthM: typeof value.width_m === "number" ? value.width_m : 6,
    colour:
      typeof value.colour === "string" && /^#[0-9a-fA-F]{6}$/.test(value.colour)
        ? value.colour
        : null,
  };
}

export function parseMotion(input: unknown): MotionData {
  if (!isRecord(input)) throw new DataError("motion must be an object");
  const nodeCount = input.node_count;
  if (typeof nodeCount !== "number" || !Number.isInteger(nodeCount) || nodeCount < 0) {
    throw new DataError("motion.node_count must be a non-negative integer");
  }
  const list = (key: "roads" | "waterways" | "rail") => {
    const value = input[key];
    if (key === "rail" && value === undefined) return [];
    if (!Array.isArray(value)) throw new DataError(`motion.${key} must be an array`);
    return value.map((path, index) => parsePath(path, `motion.${key}[${index}]`, nodeCount));
  };
  return {
    nodeCount,
    roads: list("roads"),
    waterways: list("waterways"),
    rail: list("rail"),
  };
}

export interface Edge {
  path: number;
  forward: boolean;
}

export class Network {
  readonly paths: MotionPath[];
  readonly lengths: number[];
  private readonly cumulative: number[][];
  private readonly outgoing = new Map<number, Edge[]>();

  constructor(paths: MotionPath[]) {
    this.paths = paths;
    this.cumulative = paths.map((path) => {
      const totals = [0];
      for (let index = 1; index < path.points.length; index += 1) {
        const [x0, y0] = path.points[index - 1]!;
        const [x1, y1] = path.points[index]!;
        totals.push(totals[index - 1]! + Math.hypot(x1 - x0, y1 - y0));
      }
      return totals;
    });
    this.lengths = this.cumulative.map((totals) => totals[totals.length - 1]!);
    paths.forEach((path, index) => {
      if (path.oneway !== -1) this.add(path.start, { path: index, forward: true });
      if (path.oneway !== 1) this.add(path.end, { path: index, forward: false });
    });
  }

  private add(node: number, edge: Edge) {
    const edges = this.outgoing.get(node) ?? [];
    edges.push(edge);
    this.outgoing.set(node, edges);
  }

  edgesFrom(node: number): Edge[] {
    return this.outgoing.get(node) ?? [];
  }

  /** Point and unit heading at `distance` metres along the path in its travel direction. */
  pointAt(path: number, distance: number, forward: boolean) {
    const points = this.paths[path]!.points;
    const totals = this.cumulative[path]!;
    const length = this.lengths[path]!;
    const along = Math.min(Math.max(forward ? distance : length - distance, 0), length);
    let segment = 1;
    while (segment < totals.length - 1 && totals[segment]! < along) segment += 1;
    const [x0, y0] = points[segment - 1]!;
    const [x1, y1] = points[segment]!;
    const span = totals[segment]! - totals[segment - 1]! || 1;
    const t = (along - totals[segment - 1]!) / span;
    const sign = forward ? 1 : -1;
    const dx = ((x1 - x0) / span) * sign;
    const dy = ((y1 - y0) / span) * sign;
    const norm = Math.hypot(dx, dy) || 1;
    const heights = this.paths[path]!.z;
    const z = heights ? heights[segment - 1]! + (heights[segment]! - heights[segment - 1]!) * t : 0;
    return {
      x: x0 + (x1 - x0) * t,
      y: y0 + (y1 - y0) * t,
      z,
      hx: dx / norm || 0,
      hy: dy / norm || 0,
    };
  }

  /** Next edge at the far end of the current one; avoids an immediate U-turn when possible. */
  next(current: Edge, random: () => number): Edge | null {
    const path = this.paths[current.path]!;
    const node = current.forward ? path.end : path.start;
    const options = this.edgesFrom(node);
    const onward = options.filter((edge) => edge.path !== current.path);
    const choices = onward.length > 0 ? onward : options;
    if (choices.length === 0) return null;
    return choices[Math.floor(random() * choices.length) % choices.length]!;
  }
}

export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Offset to the left of travel (Thailand drives on the left). */
export function laneOffset(
  heading: { hx: number; hy: number },
  lateralM: number,
): { dx: number; dy: number } {
  return { dx: -heading.hy * lateralM, dy: heading.hx * lateralM };
}

export interface SpawnRule {
  type: VehicleType;
  kinds: string[];
  metresPerVehicle: number;
}

export function spawn(
  network: Network,
  rules: SpawnRule[],
  seed: number,
  limit: number,
): Vehicle[] {
  const random = seededRandom(seed);
  const vehicles: Vehicle[] = [];
  let total = 0;
  network.paths.forEach((path, index) => {
    for (const rule of rules) {
      if (rule.kinds.includes(path.kind)) total += network.lengths[index]! / rule.metresPerVehicle;
    }
  });
  const thinning = Math.max(1, total / limit);
  network.paths.forEach((path, index) => {
    for (const rule of rules) {
      if (!rule.kinds.includes(path.kind)) continue;
      const expected = network.lengths[index]! / (rule.metresPerVehicle * thinning);
      let count = Math.floor(expected) + (random() < expected % 1 ? 1 : 0);
      while (count > 0 && vehicles.length < limit) {
        count -= 1;
        const forward = path.oneway === 1 ? true : path.oneway === -1 ? false : random() < 0.5;
        const twoWay = path.oneway === 0;
        const halfWidth = path.widthM / 2;
        const lateralM =
          rule.type.layer !== "waterways"
            ? twoWay
              ? halfWidth * rule.type.laneFraction
              : (random() - 0.5) * halfWidth * 0.6
            : (random() - 0.5) * 2 * halfWidth * rule.type.laneFraction;
        const bodyColour = rule.type.body[Math.floor(random() * rule.type.body.length)]!;
        vehicles.push({
          type: rule.type,
          colour: rule.type.layer === "rail" ? (path.colour ?? bodyColour) : bodyColour,
          path: index,
          forward,
          distance: random() * network.lengths[index]!,
          lateralM,
          speedMps: rule.type.speedMps * (0.85 + random() * 0.3),
        });
      }
    }
  });
  return vehicles;
}

export function advance(
  network: Network,
  vehicle: Vehicle,
  seconds: number,
  random: () => number,
): void {
  vehicle.distance += vehicle.speedMps * seconds;
  let guard = 0;
  while (vehicle.distance > network.lengths[vehicle.path]! && guard < 8) {
    guard += 1;
    vehicle.distance -= network.lengths[vehicle.path]!;
    const next = network.next({ path: vehicle.path, forward: vehicle.forward }, random);
    if (next === null) {
      vehicle.forward = !vehicle.forward;
      continue;
    }
    vehicle.path = next.path;
    vehicle.forward = next.forward;
  }
}

export type Matrix = { px: number[]; py: number[] };

export function worldToImage(matrix: Matrix, x: number, y: number, z: number): [number, number] {
  const [a, b, c, d] = matrix.px as [number, number, number, number];
  const [e, f, g, h] = matrix.py as [number, number, number, number];
  return [a * x + b * y + c * z + d, e * x + f * y + g * z + h];
}

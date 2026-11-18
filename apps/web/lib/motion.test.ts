import assert from "node:assert/strict";
import { test } from "node:test";

import {
  advance,
  laneOffset,
  Network,
  parseMotion,
  seededRandom,
  spawn,
  type VehicleType,
  worldToImage,
} from "./motion.ts";

const raw = {
  node_count: 4,
  roads: [
    { id: "a", kind: "major", start: 0, end: 1, points: [[0, 0], [100, 0]], oneway: 0, width_m: 10 },
    { id: "b", kind: "minor", start: 1, end: 2, points: [[100, 0], [100, 50]], oneway: 1, width_m: 6 },
    { id: "c", kind: "minor", start: 3, end: 1, points: [[200, 0], [100, 0]], oneway: -1, width_m: 6 },
  ],
  waterways: [{ id: "r", kind: "river", start: 0, end: 3, points: [[0, 10], [300, 10]] }],
};

const car: VehicleType = {
  name: "car",
  layer: "roads",
  lengthM: 4,
  widthM: 2,
  heightM: 1.4,
  speedMps: 10,
  body: ["#fff"],
  roof: "#ddd",
  laneFraction: 0.5,
};

test("parses motion data and rejects bad nodes", () => {
  const motion = parseMotion(raw);
  assert.equal(motion.roads.length, 3);
  assert.equal(motion.roads[1]?.oneway, 1);
  assert.equal(motion.waterways[0]?.widthM, 6);
  assert.throws(
    () => parseMotion({ ...raw, roads: [{ ...raw.roads[0], end: 9 }] }),
    /invalid start\/end/,
  );
  assert.throws(() => parseMotion({ node_count: 1, roads: [], waterways: "x" }), /waterways/);
});

test("points and headings follow travel direction", () => {
  const network = new Network(parseMotion(raw).roads);
  assert.equal(network.lengths[0], 100);
  const forward = network.pointAt(0, 25, true);
  assert.deepEqual([forward.x, forward.y, forward.hx, forward.hy], [25, 0, 1, 0]);
  const backward = network.pointAt(0, 25, false);
  assert.deepEqual([backward.x, backward.y, backward.hx, backward.hy], [75, 0, -1, 0]);
  const bend = network.pointAt(1, 10, true);
  assert.deepEqual([bend.x, bend.y], [100, 10]);
});

test("routing respects one-way streets and avoids U-turns", () => {
  const network = new Network(parseMotion(raw).roads);
  const always = () => 0;
  assert.deepEqual(network.next({ path: 0, forward: true }, always), { path: 1, forward: true });
  const fromNode1 = network.edgesFrom(1);
  assert.ok(!fromNode1.some((edge) => edge.path === 2 && edge.forward));
  assert.ok(fromNode1.some((edge) => edge.path === 0 && !edge.forward));
  assert.equal(network.next({ path: 1, forward: true }, always), null);
});

test("cars keep left of their direction of travel", () => {
  assert.deepEqual(laneOffset({ hx: 1, hy: 0 }, 2), { dx: -0, dy: 2 });
  assert.deepEqual(laneOffset({ hx: 0, hy: 1 }, 2), { dx: -2, dy: 0 });
});

test("spawning is deterministic and density based", () => {
  const network = new Network(parseMotion(raw).roads);
  const rules = [{ type: car, kinds: ["major"], metresPerVehicle: 10 }];
  const first = spawn(network, rules, 7, 100);
  const second = spawn(network, rules, 7, 100);
  assert.equal(first.length, 10);
  assert.deepEqual(first, second);
  assert.ok(first.every((vehicle) => vehicle.path === 0));
  const capped = spawn(network, rules, 7, 3);
  assert.ok(capped.length <= 3 && capped.length >= 1);
});

test("vehicles move on and turn round at dead ends", () => {
  const network = new Network(parseMotion(raw).roads);
  const vehicle = { type: car, colour: "#fff", path: 0, forward: true, distance: 95, lateralM: 2, speedMps: 10 };
  advance(network, vehicle, 1, () => 0);
  assert.equal(vehicle.path, 1);
  assert.equal(vehicle.distance, 5);
  advance(network, vehicle, 5, () => 0);
  assert.equal(vehicle.path, 1);
  assert.equal(vehicle.forward, false);
});

test("world to image uses the manifest matrix", () => {
  const matrix = { px: [2, 1, 0, 10], py: [0, -1, -3, 100] };
  assert.deepEqual(worldToImage(matrix, 5, 4, 2), [24, 90]);
});

test("seeded random repeats", () => {
  const a = seededRandom(1);
  const b = seededRandom(1);
  assert.deepEqual([a(), a(), a()], [b(), b(), b()]);
});

test("a vehicle cap thins density evenly instead of filling the first paths", () => {
  const paths = Array.from({ length: 10 }, (_, i) => ({
    id: `p${i}`,
    kind: "major",
    start: i,
    end: i + 1,
    points: [[i * 100, 0], [i * 100 + 100, 0]] as [number, number][],
    oneway: 0 as const,
    widthM: 10,
    z: null,
    colour: null,
  }));
  const network = new Network(paths);
  const vehicles = spawn(network, [{ type: car, kinds: ["major"], metresPerVehicle: 5 }], 3, 20);
  const used = new Set(vehicles.map((vehicle) => vehicle.path));
  assert.ok(vehicles.length <= 20);
  assert.ok(used.size >= 8, `only ${used.size} paths used`);
});

test("rail paths carry deck heights and line colours to trains", () => {
  const motion = parseMotion({
    node_count: 2,
    roads: [],
    waterways: [],
    rail: [
      {
        id: "way/1#0",
        kind: "metro",
        start: 0,
        end: 1,
        points: [
          [0, 0, 0],
          [100, 0, 15],
        ],
        width_m: 9,
        colour: "#65B724",
      },
    ],
  });
  const network = new Network(motion.rail);
  assert.equal(network.pointAt(0, 50, true).z, 7.5);
  const train = { ...car, layer: "rail" as const, body: ["#999999"] };
  const [vehicle] = spawn(network, [{ type: train, kinds: ["metro"], metresPerVehicle: 10 }], 1, 1);
  assert.equal(vehicle?.colour, "#65B724");
  assert.deepEqual(parseMotion({ node_count: 0, roads: [], waterways: [] }).rail, []);
});

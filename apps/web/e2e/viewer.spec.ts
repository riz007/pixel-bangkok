import { expect, type Page, test } from "@playwright/test";

const TILE_URL = /\/maps\/wat-arun\/tiles\/\d+\/\d+_\d+\.webp$/;
const PRANG = '[data-poi-id="wat-arun-central-prang"]';
const TEMPLE_COLOURS = [
  "243,234,214",
  "205,191,159",
  "150,145,132",
  "127,118,98",
  "232,184,58",
  "143,114,35",
  "42,36,48",
];

async function openMap(page: Page) {
  await page.goto("/");
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
}

async function markerAnchor(page: Page, selector: string) {
  return page.locator(selector).evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.bottom };
  });
}

async function canvasColourAt(page: Page, point: { x: number; y: number }) {
  return page.evaluate(({ x, y }) => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      ".map__canvas .openseadragon-canvas canvas",
    );
    if (!canvas) throw new Error("map canvas not found");
    const rect = canvas.getBoundingClientRect();
    const context = canvas.getContext("2d");
    if (!context) throw new Error("map canvas has no 2D context");
    const pixel = context.getImageData(
      Math.round((x - rect.left) * (canvas.width / rect.width)),
      Math.round((y - rect.top) * (canvas.height / rect.height)),
      1,
      1,
    ).data;
    return `${pixel[0]},${pixel[1]},${pixel[2]}`;
  }, point);
}

test("loads tiles for the visible area only, never the master image", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(new URL(request.url()).pathname));
  await openMap(page);
  const manifest = await (await page.request.get("/maps/wat-arun/manifest.json")).json();
  const totalTiles = manifest.tiles.levels.reduce(
    (sum: number, level: { columns: number; rows: number }) => sum + level.columns * level.rows,
    0,
  );
  const mapRequests = requests.filter((path) => path.startsWith("/maps/wat-arun/tiles/"));
  expect(mapRequests.length).toBeGreaterThan(0);
  expect(mapRequests.length).toBeLessThan(totalTiles / 2);
  for (const path of mapRequests) expect(path).toMatch(TILE_URL);
  expect(requests.some((path) => /master|render\.png/.test(path))).toBe(false);
});

test("shows at least three selectable POIs and their details", async ({ page }) => {
  await openMap(page);
  expect(await page.locator(".marker").count()).toBeGreaterThanOrEqual(3);
  await page.getByRole("button", { name: "Tha Tien Pier, Pier" }).click();
  const panel = page.getByRole("complementary");
  await expect(panel.getByRole("heading", { name: "Tha Tien Pier" })).toBeVisible();
  await expect(panel.getByText("ท่าเตียน")).toBeVisible();
  await expect(panel.locator(".poi-panel__category")).toContainText("Pier");
  await expect(panel.getByText(/East-bank pier/)).toBeVisible();
  await expect(panel.getByRole("link", { name: /OpenStreetMap way/ })).toBeVisible();
  await panel.getByRole("button", { name: "Close details" }).click();
  await expect(panel).toBeHidden();
});

test("POI marker stays on its landmark while zooming and panning", async ({ page }) => {
  const onTemple = new RegExp(`^(${TEMPLE_COLOURS.join("|")})$`);
  await openMap(page);
  await page.getByRole("button", { name: "Wat Arun Central Prang, Temple" }).click();
  for (let step = 0; step < 6; step += 1) {
    await page.getByRole("button", { name: "Zoom in" }).click();
  }
  await expect
    .poll(async () => canvasColourAt(page, await markerAnchor(page, PRANG)))
    .toMatch(onTemple);

  const before = await markerAnchor(page, PRANG);
  const box = (await page.locator(".map__canvas").boundingBox())!;
  const start = { x: box.x + box.width / 2, y: box.y + box.height * 0.25 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x - 80, start.y - 30, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await markerAnchor(page, PRANG)).x).toBeLessThan(before.x - 40);
  await expect
    .poll(async () => canvasColourAt(page, await markerAnchor(page, PRANG)))
    .toMatch(onTemple);
});

test("zoom and reset controls work from the keyboard", async ({ page }) => {
  await openMap(page);
  const home = await markerAnchor(page, PRANG);
  const tienHome = await markerAnchor(page, '[data-poi-id="tha-tien-pier"]');
  const spacing = (a: { x: number }, b: { x: number }) => Math.abs(a.x - b.x);
  const zoomIn = page.getByRole("button", { name: "Zoom in" });
  await zoomIn.focus();
  await expect(zoomIn).toBeFocused();
  await page.keyboard.press("Enter");
  await expect
    .poll(async () =>
      spacing(
        await markerAnchor(page, PRANG),
        await markerAnchor(page, '[data-poi-id="tha-tien-pier"]'),
      ),
    )
    .toBeGreaterThan(spacing(home, tienHome) * 1.3);
  await page.getByRole("button", { name: "Reset view" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await markerAnchor(page, PRANG)).x).toBeCloseTo(home.x, 0);
});

test("search finds places by Thai alias and selects them", async ({ page }) => {
  await openMap(page);
  const search = page.getByRole("searchbox");
  await search.fill("วัดแจ้ง");
  await page.getByRole("button", { name: /Wat Arun Central Prang/ }).first().click();
  await expect(page.getByRole("heading", { name: "Wat Arun Central Prang" })).toBeVisible();
  await expect(page.locator(PRANG)).toHaveAttribute("aria-pressed", "true");
  await search.fill("airport");
  await expect(page.getByText("No curated places match.")).toBeVisible();
});

test("attribution is visible and credits open in a dialog", async ({ page }) => {
  await openMap(page);
  await expect(page.getByRole("link", { name: "© OpenStreetMap contributors" })).toBeVisible();
  await page.getByRole("button", { name: "Credits" }).click();
  const dialog = page.getByRole("dialog", { name: "Credits & data" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/ODbL/)).toBeVisible();
  const manifest = await (await page.request.get("/maps/wat-arun/manifest.json")).json();
  for (const attribution of manifest.attributions) {
    await expect(dialog.getByRole("link", { name: attribution.text })).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("shows a fallback with retry when map data is unavailable", async ({ page }) => {
  let blocked = true;
  await page.route("**/maps/index.json", (route) =>
    blocked ? route.fulfill({ status: 404, body: "missing" }) : route.continue(),
  );
  await page.goto("/");
  const alert = page.getByRole("alert").filter({ hasText: "could not be loaded" });
  await expect(alert).toBeVisible();
  blocked = false;
  await alert.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
});

test("shows an error when tiles fail to load", async ({ page }) => {
  await page.route(TILE_URL, (route) => route.fulfill({ status: 500, body: "" }));
  await page.goto("/");
  await expect(page.getByText("The map image could not be loaded")).toBeVisible();
});

test("page never scrolls horizontally", async ({ page }) => {
  await openMap(page);
  const contentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(contentWidth).toBeLessThanOrEqual(page.viewportSize()!.width);
});

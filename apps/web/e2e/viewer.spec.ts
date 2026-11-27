import { expect, type Page, test } from "@playwright/test";

const TILE_URL = /\/maps\/wat-arun\/tiles\/\d+\/\d+_\d+\.webp(\?v=[\w-]+)?$/;
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

// The first-visit hint has its own test; elsewhere it would sit over pins the tests click.
test.beforeEach(async ({ page }) => {
  // Tests never reach the real weather service; the weather tests answer it themselves.
  await page.route("**/api/weather", (route) =>
    route.fulfill({ status: 503, json: { error: "weather unavailable" } }),
  );
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("keep-hint"))
      localStorage.setItem("pixel-bangkok:hint-seen", "1");
  });
});

async function openMenu(page: Page) {
  await page.getByRole("button", { name: "More map options" }).click();
}

async function openPlaces(page: Page) {
  await page.getByRole("button", { name: "Places", exact: true }).click();
}

async function openMap(page: Page) {
  await page.goto("/?area=wat-arun");
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

test("loads tiles for the visible area only, never the master image", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (request) =>
    requests.push(new URL(request.url()).pathname),
  );
  await openMap(page);
  const manifest = await (
    await page.request.get("/maps/wat-arun/manifest.json")
  ).json();
  const totalTiles = manifest.tiles.levels.reduce(
    (sum: number, level: { columns: number; rows: number }) =>
      sum + level.columns * level.rows,
    0,
  );
  const mapRequests = requests.filter((path) =>
    path.startsWith("/maps/wat-arun/tiles/"),
  );
  expect(mapRequests.length).toBeGreaterThan(0);
  expect(mapRequests.length).toBeLessThan(totalTiles / 2);
  for (const path of mapRequests) expect(path).toMatch(TILE_URL);
  expect(requests.some((path) => /master|render\.png/.test(path))).toBe(false);
});

test("shows at least three selectable POIs and their details", async ({
  page,
}) => {
  await openMap(page);
  expect(await page.locator(".marker").count()).toBeGreaterThanOrEqual(3);
  await page.locator('[data-poi-id="tha-tien-pier"]').click();
  const panel = page.getByRole("complementary");
  await expect(
    panel.getByRole("heading", { name: "Tha Tien Pier" }),
  ).toBeVisible();
  await expect(panel.getByText("ท่าเตียน")).toBeVisible();
  await expect(panel.locator(".panel__category")).toContainText("Pier");
  await expect(panel.getByText(/East-bank pier/)).toBeVisible();
  await expect(panel.getByRole("link", { name: "Read more" })).toHaveAttribute(
    "href",
    /openstreetmap\.org\/way\//,
  );
  await panel.getByRole("button", { name: "Close" }).click();
  await expect(panel).toBeHidden();
});

test("POI marker stays on its landmark while zooming and panning", async ({
  page,
}) => {
  const onTemple = new RegExp(`^(${TEMPLE_COLOURS.join("|")})$`);
  await openMap(page);
  await page.locator(PRANG).click();
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
  await expect
    .poll(async () => (await markerAnchor(page, PRANG)).x)
    .toBeLessThan(before.x - 40);
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
  await page.getByRole("button", { name: "Show all of Bangkok" }).focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(async () => (await markerAnchor(page, PRANG)).x)
    .toBeCloseTo(home.x, 0);
});

test("search finds places by Thai alias and selects them", async ({ page }) => {
  await openMap(page);
  const search = page.getByRole("searchbox");
  await search.fill("วัดแจ้ง");
  await page.locator(".search__results button").first().click();
  await expect(
    page.getByRole("heading", { name: "Wat Arun Central Prang" }),
  ).toBeVisible();
  await expect(page.locator(PRANG)).toHaveAttribute("aria-pressed", "true");
  await search.fill("airport");
  await expect(
    page.getByText("No places match. Try a Thai or English name."),
  ).toBeVisible();
});

test("attribution is visible and credits open in the About dialog", async ({
  page,
}) => {
  await openMap(page);
  await expect(
    page.getByRole("link", { name: "© OpenStreetMap contributors" }),
  ).toBeVisible();
  await openMenu(page);
  await page.getByRole("button", { name: "About", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "About this map" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.locator(".about__credits").getByText(/ODbL/),
  ).toBeVisible();
  const manifest = await (
    await page.request.get("/maps/wat-arun/manifest.json")
  ).json();
  for (const attribution of manifest.attributions) {
    await expect(
      dialog.getByRole("link", { name: attribution.text }),
    ).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("shows a fallback with retry when map data is unavailable", async ({
  page,
}) => {
  let blocked = true;
  await page.route("**/maps/index.json", (route) =>
    blocked
      ? route.fulfill({ status: 404, body: "missing" })
      : route.continue(),
  );
  await page.goto("/?area=wat-arun");
  const alert = page
    .getByRole("alert")
    .filter({ hasText: "could not be loaded" });
  await expect(alert).toBeVisible();
  blocked = false;
  await alert.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
});

test("shows an error when tiles fail to load", async ({ page }) => {
  await page.route(
    /\/maps\/wat-arun\/[a-z_]+\/\d+\/\d+_\d+\.webp(\?v=[\w-]+)?$/,
    (route) => route.fulfill({ status: 500, body: "" }),
  );
  await page.goto("/?area=wat-arun");
  // Tiles are retried three times before the viewer gives up.
  await expect(page.locator(".map__status--error")).toContainText(
    "could not be loaded",
    {
      timeout: 15_000,
    },
  );
});

test("page never scrolls horizontally", async ({ page }) => {
  await openMap(page);
  const contentWidth = await page.evaluate(
    () => document.documentElement.scrollWidth,
  );
  expect(contentWidth).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test("area selector switches to another published area", async ({ page }) => {
  const index = await (await page.request.get("/maps/index.json")).json();
  test.skip(index.areas.length < 2, "only one area published");
  await openMap(page);
  const other = index.areas.find(
    (area: { id: string }) => area.id !== "wat-arun",
  );
  await page.getByLabel("Map area").selectOption(other.id);
  await expect(page).toHaveURL(new RegExp(`area=${other.id}`));
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  await expect(page.getByLabel("Map area")).toHaveValue(other.id);
});

async function animationSignature(page: Page) {
  return page
    .locator(".map__animation:not(.map__animation--upper)")
    .evaluate((canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      if (!context || canvas.width === 0) return { painted: 0, hash: 0 };
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let painted = 0;
      let hash = 0;
      for (let index = 3; index < data.length; index += 4) {
        if (data[index]! > 0) {
          painted += 1;
          hash = (hash * 31 + index + data[index - 3]!) % 1_000_000_007;
        }
      }
      return { painted, hash };
    });
}

test("traffic and boats draw when zoomed in and the toggle controls motion", async ({
  page,
}) => {
  const index = await (await page.request.get("/maps/index.json")).json();
  test.skip(
    !index.areas.some((area: { id: string }) => area.id === "old-town"),
    "old-town not published",
  );
  await page.goto("/?area=old-town");
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  const toggle = page.getByRole("switch", { name: /traffic and boats/ });
  await openMenu(page);
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await page.keyboard.press("Escape");
  await page.getByRole("searchbox").fill("Memorial Bridge");
  await page.locator(".search__results button").first().click();
  await page
    .getByRole("complementary")
    .getByRole("button", { name: "Close" })
    .click();
  for (let step = 0; step < 6; step += 1) {
    await page.getByRole("button", { name: "Zoom in" }).click();
  }
  await expect
    .poll(async () => (await animationSignature(page)).painted)
    .toBeGreaterThan(50);
  await page.waitForTimeout(200);
  const still = await animationSignature(page);
  await page.waitForTimeout(400);
  expect((await animationSignature(page)).hash).toBe(still.hash);

  await openMenu(page);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await expect
    .poll(async () => (await animationSignature(page)).hash)
    .not.toBe(still.hash);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
});

test("animation layer stays empty when zoomed far out", async ({ page }) => {
  const index = await (await page.request.get("/maps/index.json")).json();
  test.skip(
    !index.areas.some((area: { id: string }) => area.id === "old-town"),
    "old-town not published",
  );
  await page.goto("/?area=old-town");
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  await openMenu(page);
  await expect(
    page.getByRole("switch", { name: /traffic and boats/ }),
  ).toBeVisible();
  await page.waitForTimeout(300);
  expect((await animationSignature(page)).painted).toBe(0);
});

test("about shows the full ceremonial name of Bangkok", async ({ page }) => {
  await openMap(page);
  await page.getByRole("button", { name: /Pixel Bangkok, Bangkok/ }).click();
  const dialog = page.getByRole("dialog", { name: "About this map" });
  await expect(dialog.getByText(/^กรุงเทพมหานคร อมรรัตนโกสินทร์/)).toBeVisible();
  await expect(
    dialog.getByText(/^Krung Thep Mahanakhon Amon Rattanakosin/),
  ).toBeVisible();
});

test("language switch changes the interface and is remembered", async ({
  page,
}) => {
  await openMap(page);
  await expect(page.getByRole("searchbox")).toHaveAttribute(
    "placeholder",
    "A place, or lat, long",
  );
  await openMenu(page);
  await page.getByRole("button", { name: "Switch to Thai" }).click();
  await expect(page.getByRole("searchbox")).toHaveAttribute(
    "placeholder",
    "สถานที่ หรือ ละติจูด, ลองจิจูด",
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "th");
  await page.reload();
  await expect(page.getByRole("searchbox")).toHaveAttribute(
    "placeholder",
    "สถานที่ หรือ ละติจูด, ลองจิจูด",
  );
  await page.getByRole("button", { name: "ตัวเลือกแผนที่เพิ่มเติม" }).click();
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(page.getByRole("searchbox")).toHaveAttribute(
    "placeholder",
    "A place, or lat, long",
  );
});

test("places rail selects places in walking order and deep links work", async ({
  page,
  isMobile,
}) => {
  await openMap(page);
  await openPlaces(page);
  const rail = page.getByRole("region", { name: /Places to visit/ });
  const first = rail.locator(".plate").first();
  await first.click();
  if (isMobile) {
    await expect(rail).toBeHidden();
    await openPlaces(page);
  }
  await expect(first).toHaveAttribute("aria-current", "true");
  await expect(page).toHaveURL(/place=/);
  const placeId = new URL(page.url()).searchParams.get("place");
  const next = rail.getByRole("button", { name: "Next place" });
  if (await next.isVisible()) await next.click();
  else await rail.locator(".plate").nth(1).click();
  if (isMobile) {
    await expect(rail).toBeHidden();
    await openPlaces(page);
  }
  await expect(rail.locator(".plate").nth(1)).toHaveAttribute(
    "aria-current",
    "true",
  );

  await page.goto(`/?area=wat-arun&place=${placeId}`);
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  await expect(page.getByRole("complementary")).toBeVisible();
  await expect(page.locator(`[data-poi-id="${placeId}"]`)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("slash focuses search and P toggles the places rail", async ({ page }) => {
  await openMap(page);
  await page.keyboard.press("/");
  await expect(page.getByRole("searchbox")).toBeFocused();
  await page.getByRole("searchbox").blur();
  await expect(
    page.getByRole("region", { name: /Places to visit/ }),
  ).toBeHidden();
  await page.keyboard.press("p");
  await expect(
    page.getByRole("region", { name: /Places to visit/ }),
  ).toBeVisible();
  await page.keyboard.press("p");
  await expect(
    page.getByRole("region", { name: /Places to visit/ }),
  ).toBeHidden();
});

test("lat, long search drops a pin on the matching map point", async ({
  page,
}) => {
  await openMap(page);
  const search = page.getByRole("searchbox");
  await search.fill("13.7437, 100.48889");
  await page.getByRole("button", { name: "Go to 13.74370, 100.48889" }).click();
  const pin = page.getByRole("img", { name: "Searched location" });
  await expect(pin).toBeVisible();
  await expect
    .poll(async () => {
      const prang = await markerAnchor(page, PRANG);
      const box = await page.locator(".map__pin").evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return { x: rect.left, y: rect.top };
      });
      return Math.hypot(prang.x - box.x, prang.y - box.y);
    })
    .toBeLessThan(6);
  await search.fill("13.9, 100.6");
  await expect(
    page.getByText("That point is outside this map area.").first(),
  ).toBeVisible();
});

test("report opens an OpenStreetMap note at the current view", async ({
  page,
}) => {
  await openMap(page);
  await page.evaluate(() => {
    (window as unknown as { opened: string[] }).opened = [];
    window.open = (url) => {
      (window as unknown as { opened: string[] }).opened.push(String(url));
      return null;
    };
  });
  await openMenu(page);
  await page.getByRole("button", { name: /Report a map error/ }).click();
  const opened = await page.evaluate(
    () => (window as unknown as { opened: string[] }).opened,
  );
  expect(opened).toHaveLength(1);
  expect(opened[0]).toMatch(
    /^https:\/\/www\.openstreetmap\.org\/note\/new#map=18\/13\.74\d+\/100\.48\d+$/,
  );
});

test("place filters narrow the pins and the places strip and are shareable", async ({
  page,
}) => {
  await openMap(page);
  await openPlaces(page);
  const filters = page.getByRole("group", { name: "Show places by type" });
  const all = await page.locator(".marker").count();
  const worship = filters.getByRole("button", { name: /Places of worship/ });
  await worship.click();
  await expect(worship).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/filter=worship/);
  const shown = await page.locator(".marker").count();
  expect(shown).toBeGreaterThan(0);
  expect(shown).toBeLessThan(all);
  await filters.getByRole("button", { name: /^All/ }).click();
  await expect(page.locator(".marker")).toHaveCount(all);
  await expect(page).not.toHaveURL(/filter=/);
});

test("places and their filters start hidden, and phone credits collapse to OpenStreetMap", async ({
  page,
  isMobile,
}) => {
  await openMap(page);
  const filters = page.getByRole("group", { name: "Show places by type" });
  await expect(filters).toHaveCount(0);
  await openPlaces(page);
  await expect(filters).toBeVisible();
  await page.getByRole("button", { name: "Close the places list" }).click();
  await expect(filters).toHaveCount(0);
  const credit = page.locator(".credit");
  await expect(
    credit.getByRole("link", { name: /OpenStreetMap/ }),
  ).toBeVisible();
  const more = credit.getByRole("link", { name: /Tree canopy/ });
  if (isMobile) {
    await expect(more).toBeHidden();
    await credit.getByRole("button", { name: "Show all map credits" }).click();
  }
  await expect(more).toBeVisible();
});

test("About shows the Isometric Cities badge", async ({ page }) => {
  await openMap(page);
  await openMenu(page);
  await page.getByRole("button", { name: "About", exact: true }).click();
  const badge = page.locator(".about__badge").getByRole("link", {
    name: "Featured on Isometric Cities",
  });
  await expect(badge).toHaveAttribute("href", "https://isometriccities.com/");
});

test("AI art is off by default and switches the map to AI tiles", async ({
  page,
}) => {
  const manifest = await (
    await page.request.get("/maps/old-town/manifest.json")
  ).json();
  test.skip(!manifest.ai, "no AI layer published for old-town");
  const requests: string[] = [];
  page.on("request", (request) =>
    requests.push(new URL(request.url()).pathname),
  );
  await page.goto("/?area=old-town");
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  const toggle = page.getByRole("button", { name: "Show AI art" });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  expect(requests.some((path) => path.startsWith("/maps/old-town/ai/"))).toBe(
    false,
  );
  await toggle.click();
  await expect(
    page.getByRole("button", { name: "Show the plain drawing" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(() => requests.some((path) => path.startsWith("/maps/old-town/ai/")))
    .toBe(true);
});

test("the Isometric Cities badge shows on the map and stays hidden once dismissed", async ({
  page,
}) => {
  await openMap(page);
  const badge = page.locator(".featured");
  await expect(badge.getByRole("link")).toHaveAttribute(
    "href",
    "https://isometriccities.com/cities/bangkok/",
  );
  await badge
    .getByRole("button", { name: "Hide the Isometric Cities badge" })
    .click();
  await expect(badge).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  await expect(badge).toHaveCount(0);
});

test("a first visit shows one hint that opens the places list and stays dismissed", async ({
  page,
}) => {
  await page.addInitScript(() => sessionStorage.setItem("keep-hint", "1"));
  await page.goto("/?area=wat-arun");
  await page.evaluate(() => localStorage.removeItem("pixel-bangkok:hint-seen"));
  await page.reload();
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  const hint = page.locator(".hint");
  await expect(hint).toContainText("Drag to explore");
  await hint.getByRole("button", { name: "Browse places" }).click();
  await expect(
    page.getByRole("region", { name: /Places to visit/ }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  await expect(page.locator(".hint")).toHaveCount(0);
});

test("the More menu holds the secondary controls and closes after an action", async ({
  page,
}) => {
  await openMap(page);
  const about = page.getByRole("button", { name: "About", exact: true });
  await expect(about).toBeHidden();
  await openMenu(page);
  await expect(about).toBeVisible();
  await expect(page.getByRole("switch", { name: "Labels" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(about).toBeHidden();
  await openMenu(page);
  await about.click();
  await expect(
    page.getByRole("dialog", { name: "About this map" }),
  ).toBeVisible();
  await expect(about).toBeHidden();
});

test("day and night follow Bangkok time, and a chosen light mode is remembered", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-11-27T22:00:00+07:00") });
  await openMap(page);
  const sky = page.locator(".map__sky");
  await expect(sky).toHaveAttribute("data-phase", "night");
  await openMenu(page);
  const lights = page.getByRole("group", { name: /Bangkok time now 22:00/ });
  await expect(
    lights.getByRole("button", { name: "Follow Bangkok time" }),
  ).toHaveAttribute("aria-pressed", "true");
  await lights.getByRole("button", { name: "Day", exact: true }).click();
  await expect(sky).toHaveAttribute("data-phase", "day");
  await page.reload();
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  await expect(page.locator(".map__sky")).toHaveAttribute("data-phase", "day");
});

test("at midday in Bangkok the map is in daylight", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-11-27T12:00:00+07:00") });
  await openMap(page);
  await expect(page.locator(".map__sky")).toHaveAttribute("data-phase", "day");
  await page.keyboard.press("n");
  await expect(page.locator(".map__sky")).toHaveAttribute("data-phase", "day");
  await page.keyboard.press("n");
  await expect(page.locator(".map__sky")).toHaveAttribute(
    "data-phase",
    "night",
  );
});

const RAIN = {
  observedAt: "2026-11-27T19:15",
  temperatureC: 29.6,
  condition: "rain",
  precipitationMm: 2.4,
  cloudCover: 100,
  windKmh: 12,
  pm25: 52.4,
  aqi: 142,
  aqiBand: "sensitive",
};

test("live weather rains on the map and shows the reading, and W turns it off", async ({
  page,
}) => {
  await page.route("**/api/weather", (route) => route.fulfill({ json: RAIN }));
  await openMap(page);
  const layer = page.locator(".map__weather");
  await expect(layer).toHaveAttribute("data-condition", "rain");
  await expect(layer.locator(".map__rain")).toHaveCount(1);
  const reading = page.locator(".weather");
  await expect(reading).toContainText("30°");
  await expect(reading).toContainText("Rain");
  await expect(reading).toContainText("PM2.5 52");
  await expect(reading).toHaveAttribute(
    "aria-label",
    /US AQI 142, unhealthy for sensitive groups/,
  );
  await expect(
    page.locator(".credit a", { hasText: "Open-Meteo" }),
  ).toBeAttached();
  await page.keyboard.press("w");
  await expect(layer).toHaveCount(0);
  await expect(reading).toHaveCount(0);
});

test("the map works the same when the weather service is down", async ({
  page,
}) => {
  await openMap(page);
  await expect(page.locator(".map__weather")).toHaveCount(0);
  await expect(page.locator(".weather")).toHaveCount(0);
  await expect(page.locator(".marker").first()).toBeVisible();
});

test("lit windows load only after dark and fade in with the night", async ({
  page,
}) => {
  const manifest = await (
    await page.request.get("/maps/old-town/manifest.json")
  ).json();
  test.skip(
    !manifest.animation?.lights_url_template,
    "no lights layer published for old-town",
  );
  const requests: string[] = [];
  page.on("request", (request) =>
    requests.push(new URL(request.url()).pathname),
  );
  await page.clock.install({ time: new Date("2026-11-27T12:00:00+07:00") });
  await page.goto("/?area=old-town");
  await expect(page.locator(".map")).toHaveAttribute("data-status", "ready");
  const lights = page.locator(".map__lights");
  await expect(lights).toHaveCSS("opacity", "0");
  expect(
    requests.some((path) => path.startsWith("/maps/old-town/lights/")),
  ).toBe(false);
  await page.keyboard.press("n");
  await page.keyboard.press("n");
  await expect(page.locator(".map__sky")).toHaveAttribute(
    "data-phase",
    "night",
  );
  await expect
    .poll(() =>
      requests.some((path) => path.startsWith("/maps/old-town/lights/")),
    )
    .toBe(true);
  await expect(lights.locator("canvas")).toHaveCount(1);
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("a place link already carries the place's card for search engines", async ({
    page,
  }) => {
    await page.goto("/?area=old-town&place=democracy-monument");
    const card = page.getByRole("complementary");
    await expect(
      card.getByRole("heading", {
        name: /Democracy Monument|อนุสาวรีย์ประชาธิปไตย/,
      }),
    ).toBeVisible();
    await expect(card).toContainText("13.75667");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      /\?area=bangkok&place=democracy-monument$/,
    );
  });
});

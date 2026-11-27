import { expect, test } from "@playwright/test";

const portfolioSections = [
  "top",
  "core-release",
  "capabilities",
  "architecture",
  "session",
  "prerequisites",
  "roadmap",
  "projects"
];

const pageRoutes = ["/", "/live.html", "/cv.html", "/core.html", "/start-here.html", "/wow.html"];
const viewportWidths = [320, 375, 390, 768, 1024, 1365];

test("homepage navigation points to real sections and portfolio pages", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/ANA MAX OS29/);
  const mainHeading = page.getByRole("heading", { level: 1 });
  await expect(mainHeading).toContainText("Don't start over.");
  await expect(mainHeading).toContainText("Keep the proof.");

  for (const id of portfolioSections) {
    await expect(page.locator("#" + id), "missing section #" + id).toHaveCount(1);
  }

  const internalHrefs = await page.locator('a[href^="#"]').evaluateAll((links) =>
    links.map((link) => link.getAttribute("href")).filter(Boolean)
  );
  expect(internalHrefs.length).toBeGreaterThan(0);
  for (const href of internalHrefs) {
    await expect(page.locator(href), "broken in-page link " + href).toHaveCount(1);
  }

  await expect(page.locator('a[href="./start-here.html"]').first()).toBeVisible();
  await expect(page.locator('a[href="./live.html"]').first()).toBeVisible();
  await expect(page.locator('a[href="./cv.html"]').first()).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("the four portfolio pages load without uncaught JavaScript errors", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  for (const route of pageRoutes) {
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), "unexpected status for " + route).toBe(200);
    await expect(page.locator("h1").first(), "missing heading on " + route).toBeVisible();
  }

  expect(pageErrors).toEqual([]);
});

test("portfolio layouts do not overflow at common mobile and desktop widths", async ({ page }) => {
  for (const route of pageRoutes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    for (const width of viewportWidths) {
      await page.setViewportSize({ width, height: 800 });
      const dimensions = await page.evaluate(() => ({
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth
      }));
      expect(
        dimensions.documentWidth,
        route + " overflows horizontally at viewport width " + width
      ).toBeLessThanOrEqual(dimensions.viewportWidth);
    }
  }
});

test("Tower demo advances, hands off, verifies and resets with no remote requests", async ({ page }) => {
  const errors = [], external = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("request", r => { if (!r.url().startsWith("http://127.0.0.1:4173/")) external.push(r.url()); });
  await page.goto("/live.html");
  await expect(page.locator("h1")).toContainText("TOWER CONTROL");
  await expect(page.getByText("PUBLIC DEMO", {exact:true})).toBeVisible();
  await expect(page.locator("#nextAction")).toContainText("Reproduce");
  await page.locator("#advance").click();
  await expect(page.locator("#owner")).toContainText("Qwen");
  await page.locator("#advance").click();
  await expect(page.locator("#owner")).toContainText("GPT-6");
  await page.locator("#advance").click();
  await expect(page.locator("#gateState")).toHaveText("PASS");
  await page.getByRole("button", {name:"View evidence in Work Units"}).click();
  await expect(page.locator("#workDetail")).toContainText("7/7");
  await page.locator("#nav-dashboard").click();
  await page.locator("#reset").click();
  await expect(page.locator("#gateState")).toHaveText("PENDING");
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("all Tower views work, service simulation and tool filters stay local", async ({ page }) => {
  await page.goto("/live.html");
  for (const id of ["services","config","inventory","profiles","logs","workunits","terminals","architecture","frida","gpt","dashboard"]) {
    await page.locator("#nav-"+id).click();
    await expect(page.locator("#view-"+id)).toBeVisible();
  }
  await page.locator("#nav-services").click();
  await page.locator("#serviceSearch").fill("ANA MAX");
  await expect(page.locator("#serviceList .service")).toHaveCount(1);
  await page.locator("#serviceList").getByRole("button",{name:"Simulate stop"}).click();
  await page.locator("#toolSearch").fill("os29_trace_get");
  await expect(page.locator("#toolCatalog .service")).toHaveCount(1);
  await page.locator("#nav-dashboard").click();
  await expect(page.locator("#labState")).toHaveText("DEGRADED");
  await page.locator("#reset").click();
  await expect(page.locator("#labState")).toHaveText("READY");
  await expect(page.locator("img").first()).toHaveJSProperty("complete",true);
  expect(await page.locator("img").first().evaluate(img=>img.naturalWidth)).toBeGreaterThan(0);
});

test("historical repair is honest, translated, and does not expose local paths", async ({ page }) => {
  await page.goto("/wow.html");
  await expect(page.getByRole("heading",{level:1})).toContainText("One real bug.");
  await expect(page.locator("main")).toContainText("433/433");
  await expect(page.locator("main")).toContainText("Qwen 7B did not pass all tests on its own");
  await expect(page.locator("main")).toContainText("historical local results");
  expect(await page.locator("body").innerText()).not.toMatch(/C:\\Users\\|D:\\OS28_MEMORY|127\.0\.0\.1/);
});
test("CV page exposes its title, Tower Control link and print control", async ({ page }) => {
  await page.goto("/cv.html");
  await expect(page).toHaveTitle(/Professional CV \| ANA MAX/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Clear evidence.");
  await expect(page.getByRole("link", { name: /Tower Control/i })).toBeVisible();
  await expect(page.getByText("Print / Save PDF", { exact: true })).toBeVisible();
});


test("verified OS29 Core v0.1.0 is visible from the home page", async ({ page }) => {
  await page.goto("/");
  const featured = page.locator("#core-release");
  await expect(featured.getByRole("heading", { name: /OS29 Core v0\.1\.0/i })).toBeVisible();
  await expect(featured).toContainText("91");
  await expect(featured.getByRole("link", { name: /Explore the release/i })).toHaveAttribute("href", "./core.html");
  await expect(featured.getByRole("link", { name: /Official v0\.1\.0/i })).toHaveAttribute(
    "href",
    "https://github.com/gyodragos-cell/ana-max-os29-core/releases/tag/v0.1.0"
  );
  await page.getByRole("link", { name: /Explore OS29 Core/i }).first().click();
  await expect(page).toHaveURL(/core\.html$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Memory that");
});

test("Core release has the exact published links, install command and no private data", async ({ page }) => {
  await page.goto("/core.html");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("keeps the work moving.");
  await expect(page.locator(".brand .mark")).toHaveCSS("font-size", "20px");
  await expect(page.getByRole("link", { name: /Get v0\.1\.0/i })).toHaveAttribute(
    "href",
    "https://github.com/gyodragos-cell/ana-max-os29-core/releases/tag/v0.1.0"
  );
  const commands = await page.locator("#windows-commands").textContent();
  expect(commands).toContain("git clone --branch v0.1.0 https://github.com/gyodragos-cell/ana-max-os29-core.git");
  expect(commands).not.toMatch(/C:\\Users\\|D:\\OS28_MEMORY|PC1313/);
  await expect(page.getByRole("link", { name: /View verification CI/i })).toHaveAttribute(
    "href",
    "https://github.com/gyodragos-cell/ana-max-os29-core/actions/runs/44537253988"
  );
});

test("direct OS28 tool link opens the catalog", async ({page}) => {
  await page.goto("/live.html#services");
  await expect(page.locator("#view-services")).toBeVisible();
  await expect(page.locator("#toolCatalog")).toContainText("os29_work_unit_resume");
  await expect(page.getByText("Bridge catalog entries")).toBeVisible();
});
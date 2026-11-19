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

const pageRoutes = ["/", "/live.html", "/cv.html", "/core.html"];
const viewportWidths = [320, 375, 390, 768, 1024, 1365];

test("homepage navigation points to real sections and portfolio pages", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/ANA MAX OS29/);
  const mainHeading = page.getByRole("heading", { level: 1 });
  await expect(mainHeading).toContainText("Build local tools.");
  await expect(mainHeading).toContainText("Keep evidence.");

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

  await expect(page.locator('a[href="./live.html"]').first()).toBeVisible();
  await expect(page.locator('a[href="./cv.html"]').first()).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("the three portfolio pages load without uncaught JavaScript errors", async ({ page }) => {
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

test("Live Profile personalizes locally without submitting the chosen name", async ({ page }) => {
  const displayName = "Playwright QA Probe";
  const requestsContainingName = [];
  page.on("request", (request) => {
    const body = request.postData() || "";
    if (request.url().includes(encodeURIComponent(displayName)) || body.includes(displayName)) {
      requestsContainingName.push(request.url());
    }
  });

  await page.goto("/live.html");
  await page.getByLabel("Choose a display name").fill(displayName);
  await page.getByRole("button", { name: "Set my profile" }).click();

  await expect(page.locator("#profileName")).toHaveText(displayName);
  await expect(page.locator("#greeting")).toHaveText(displayName);
  await expect(page.locator("#avatar")).toHaveText("P");
  expect(new URL(page.url()).search).toBe("");
  expect(requestsContainingName).toEqual([]);
});

test("Live Profile shows its local status sample", async ({ page }) => {
  await page.goto("/live.html");
  await expect(page.locator("#connBadge")).not.toHaveText("Checking…");
  await expect(page.locator("#updatedAt")).toContainText("LOCAL SAMPLE");
  await expect(page.locator("#networkState")).not.toHaveText("—");
  await expect(page.locator("#uptime")).not.toHaveText("0 seconds");
});

test("CV page exposes its title, Live Profile link and print control", async ({ page }) => {
  await page.goto("/cv.html");
  await expect(page).toHaveTitle(/Professional CV \| ANA MAX/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Clear evidence.");
  await expect(page.getByRole("link", { name: /Live Profile/i })).toBeVisible();
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

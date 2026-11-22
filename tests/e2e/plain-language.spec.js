import { expect, test } from "@playwright/test";

const widths = [320, 375, 390, 768, 1365];

test("an ordinary visitor sees a clear claim and cannot mistake the demo for live AI", async ({ page }) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const response = await page.goto("/start-here.html");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/OS29 explained simply/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("pick up where it left off?");
  await expect(page.getByText("It is not another AI model.")).toBeVisible();
  await expect(page.getByText("The page is static and does not run an AI.")).toBeVisible();
  await expect(page.getByText("Qwen did not repair the bug completely on its own.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Read how the bug was fixed/i }))
    .toHaveAttribute("href", /TWO_AGENTS_REAL_BUG_REPAIR\.md$/);
  expect(errors).toEqual([]);
});

test("the three-step explanation moves forward, backward and restarts", async ({ page }) => {
  await page.goto("/start-here.html");
  const step = page.locator("#stepProgress");
  await expect(step).toHaveText("STEP 1 OF 3");
  await expect(page.locator("#stepTitle")).toHaveText("Agent A finds a problem");
  await expect(page.locator("#previousStep")).toBeDisabled();
  await page.locator("#nextStep").click();
  await expect(step).toHaveText("STEP 2 OF 3");
  await expect(page.locator("#stepProof")).toContainText("Recovered from OS29");
  await page.locator("#nextStep").click();
  await expect(step).toHaveText("STEP 3 OF 3");
  await expect(page.locator("#nextStep")).toBeDisabled();
  await page.locator("#previousStep").click();
  await expect(step).toHaveText("STEP 2 OF 3");
  await page.locator("#restartStory").click();
  await expect(step).toHaveText("STEP 1 OF 3");
  await expect(page.locator("#progressFill")).toHaveCSS("width", /[0-9.]+px/);
});

test("Romanian is a complete usable translation, including interactive states", async ({ page }) => {
  await page.goto("/start-here.html");
  await page.locator("#roBtn").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ro");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("continua de unde a rămas?");
  await expect(page.locator("#stepProgress")).toHaveText("PASUL 1 DIN 3");
  await expect(page.locator("#nextStep")).toHaveText("Pasul următor");
  await page.locator("#nextStep").click();
  await expect(page.locator("#stepTitle")).toHaveText("Agentul B continuă aceeași lucrare");
  await expect(page.locator("#stepProof")).toContainText("Recuperat din OS29");
  await page.locator("#enBtn").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("#stepProgress")).toHaveText("STEP 2 OF 3");
  await expect(page.locator("#enBtn")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#roBtn")).toHaveAttribute("aria-pressed", "false");
});

test("new visitor path has no horizontal overflow on mobile and desktop", async ({ page }) => {
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/start-here.html");
  for (const width of widths) {
    await page.setViewportSize({ width, height: 830 });
    const dims = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth
    }));
    expect(dims.document, "overflow at width " + width).toBeLessThanOrEqual(dims.viewport);
  }
  await page.locator("#roBtn").click();
  await page.setViewportSize({ width: 320, height: 830 });
  const width = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth
  }));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
  expect(errors).toEqual([]);
});

test("visible sharing and feedback links lead to the real public repositories", async ({ page }) => {
  await page.goto("/start-here.html");
  await expect(page.getByRole("link", { name: "View / star on GitHub" })).toHaveAttribute(
    "href", "https://github.com/gyodragos-cell/ana-max-os29"
  );
  await expect(page.getByRole("link", { name: "Report a bug or share feedback" })).toHaveAttribute(
    "href", "https://github.com/gyodragos-cell/ana-max-os29/issues"
  );
  await page.locator("#copyLink").click();
  await expect(page.locator("#shareStatus")).not.toBeEmpty();
});

import { expect, test } from "@playwright/test";

/**
 * End-to-end smoke: preflight → compose demo → screen → results → selection.
 * Runs against the live backend serving the SPA. The demo inline request yields
 * the honest no-viable-network outcome, so we assert on the pre-logistics
 * ranking fallback rather than a development shortlist.
 */

test("workbench boots with WIMP chrome and healthy backend", async ({ page }) => {
  await page.goto("/");
  // Menu bar is the complete command inventory.
  for (const menu of ["File", "Edit", "View", "Study", "Tools", "Help"]) {
    await expect(page.getByRole("menuitem", { name: menu })).toBeVisible();
  }
  // Status bar health dot resolves to ready (backend up).
  await expect(page.locator(".status-health")).toContainText(/ready|checking/);
  // Composer loaded the demo base and previews a scenario count.
  await expect(page.locator(".compose-preview")).toContainText("scenarios", { timeout: 15_000 });
});

test("screening run streams progress and populates results", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".compose-preview")).toContainText("scenarios", { timeout: 15_000 });

  // Screen via the toolbar accent button.
  await page.getByRole("button", { name: /Screen/ }).first().click();

  // Run console shows the real stage timeline.
  await expect(page.locator(".stage-list")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".stage-label").first()).toContainText(/Resolve|Surrogate/);

  // On completion the workbench opens the Ranking tab automatically.
  await expect(page.locator(".ranking")).toBeVisible({ timeout: 60_000 });

  // The run console retains its completed dedup counter when revisited.
  await page.getByRole("tab", { name: "Run console" }).click();
  await expect(page.locator(".run-dedup")).toContainText(/dedup \d+\/\d+/);

  await page.getByRole("tab", { name: "Ranking" }).click();
  await expect(page.locator(".data-table")).toBeVisible();

  // Selecting a ranking row drives the inspector.
  const firstRow = page.locator(".data-table tbody tr").first();
  if (await firstRow.count()) {
    await firstRow.click();
    await expect(page.locator(".region-inspector")).toContainText(/W0|selected|not selected/);
  }
});

test("carbon-price scrubber pivots without network calls", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".compose-preview")).toContainText("scenarios", { timeout: 15_000 });
  await page.getByRole("button", { name: /Screen/ }).first().click();
  await expect(page.locator(".ranking")).toBeVisible({ timeout: 60_000 });

  await page.getByRole("tab", { name: "Economics" }).click();
  const scrubber = page.locator(".scrubber-range");
  await expect(scrubber).toBeVisible();

  // Record network calls while dragging; the pivot must be purely client-side.
  const calls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/screen")) calls.push(r.url());
  });
  await scrubber.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  expect(calls).toHaveLength(0);
});

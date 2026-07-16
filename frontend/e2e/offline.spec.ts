import { expect, test } from "@playwright/test";

/**
 * Offline resilience: the SPA and its bundled assets load, but every API call
 * fails (flaky-wifi / backend-down). The cached demo result must still populate
 * the workbench and the client-side scrubber must still work (design §8).
 */
test("offline: cached demo renders when the API is unreachable", async ({ page }) => {
  // Abort all API calls; static assets (/assets/*, JS, CSS) still load.
  await page.route("**/health", (r) => r.abort());
  await page.route("**/presets", (r) => r.abort());
  await page.route("**/screen**", (r) => r.abort());

  await page.goto("/");
  // Health dot resolves to unreachable.
  await expect(page.locator(".status-health")).toContainText(/unreachable|degraded/, { timeout: 15000 });
  // The cached demo result populated the ledger.
  await expect(page.locator(".region-tree")).toContainText("imported", { timeout: 15000 });
  // Ranking works from cached data.
  await page.getByRole("tab", { name: "Ranking" }).click();
  await expect(page.locator(".data-table")).toBeVisible();
  // Scrubber (client-side pivot) works with no backend.
  await page.getByRole("tab", { name: "Economics" }).click();
  await expect(page.locator(".scrubber-range")).toBeVisible();
});

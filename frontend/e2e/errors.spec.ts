import { expect, test } from "@playwright/test";

/** HTTP error mapping (design §8): 503 -> dependency banner; 422 -> composer. */
test("503 from screen maps to a dependency banner", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".compose-preview")).toContainText("scenarios", { timeout: 15000 });
  // Force the stream and sync fallback to 503.
  await page.route("**/screen/stream", (r) => r.fulfill({ status: 503, body: "checkpoint is not loaded" }));
  await page.route("**/screen", (r) => r.fulfill({ status: 503, body: "checkpoint is not loaded" }));
  await page.getByRole("button", { name: /Screen/ }).first().click();
  await expect(page.locator(".banner-danger")).toContainText(/dependency|unavailable/i, { timeout: 15000 });
});

test("422 from screen surfaces on the composer", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".compose-preview")).toContainText("scenarios", { timeout: 15000 });
  const body = JSON.stringify({ detail: [{ type: "value_error", loc: ["body", "carbon_prices"], msg: "too few" }] });
  await page.route("**/screen/stream", (r) => r.fulfill({ status: 422, contentType: "application/json", body }));
  await page.route("**/screen", (r) => r.fulfill({ status: 422, contentType: "application/json", body }));
  await page.getByRole("button", { name: /Screen/ }).first().click();
  await expect(page.locator(".banner-warning")).toContainText(/Invalid request/i, { timeout: 15000 });
  await expect(page.getByRole("tab", { name: "Compose" })).toHaveAttribute("data-state", "active");
});

import { test } from "@playwright/test";

// Captures the images used by the README and the portfolio card. Runs only when SCREENSHOT_DIR is set.
const dir = process.env.SCREENSHOT_DIR;

test("screenshots", async ({ page }, info) => {
  test.skip(!dir || info.project.name !== "desktop", "set SCREENSHOT_DIR to capture screenshots");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("./?run=invoicing");
  await page.getByRole("button", { name: "4x" }).click();
  await page.getByText("Needs your review").waitFor({ timeout: 20_000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${dir}/demo.png` });

  const review = page.getByRole("region", { name: "Human review" });
  await review.getByLabel("Dismiss Hardcoded password or secret").check();
  await review.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("region", { name: "PR description" }).waitFor();
  await page.getByRole("region", { name: "Result" }).screenshot({ path: `${dir}/demo-report.png` });
});

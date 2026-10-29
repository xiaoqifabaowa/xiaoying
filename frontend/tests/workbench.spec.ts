import { test, expect, type Page } from "@playwright/test";

async function mockMode(page: Page) {
  await page.goto("/");
  await page.getByTitle("● 真实模型", { exact: true }).click();
  await page.getByTitle("◌ 离线 Mock", { exact: true }).click();
  await expect(
    page.getByText(
      "离线 Mock：脚本只验证流程，不证明真实模型决策与语义审核效果。",
    ),
  ).toBeVisible();
}

test("normal answer, source highlighting, trace and conversation reload", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await mockMode(page);
  await page.getByRole("textbox", { name: "输入问题" }).fill("报销期限多久？");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.getByText("已核验回答", { exact: true })).toBeVisible();
  await expect(page.locator(".answer-text")).toContainText("30 天");
  await page.locator(".evidence-card").first().click();
  await expect(page.locator(".source-paragraph.highlighted")).toContainText(
    "30 天",
  );
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: /执行记录/ }).click();
  await expect(
    page.getByRole("link", { name: "下载完整 Trace" }),
  ).toBeVisible();
  await expect(page.locator(".trace-list")).toContainText("审核通过");
  await page
    .getByRole("textbox", { name: "输入问题" })
    .fill("那需要准备哪些材料？");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.locator(".answer-text").last()).toContainText("有效发票");
  await page.screenshot({
    path: "../examples/screenshots/answer.png",
    fullPage: true,
  });
  await page.reload();
  await page
    .locator(".history-item")
    .filter({ hasText: "报销期限多久？" })
    .first()
    .click();
  await expect(page.locator(".answer-text").last()).toContainText("有效发票");
  expect(errors).toEqual([]);
});

test("conflict scenario keeps both citations and requests clarification", async ({
  page,
}) => {
  await mockMode(page);
  await page.getByRole("button", { name: "评审用例", exact: true }).click();
  const card = page.locator(".scenario-card").filter({
    has: page.getByRole("heading", { name: "制度冲突", exact: true }),
  });
  await card.getByRole("button", { name: /运行场景/ }).click();
  await expect(page.getByText("制度存在冲突", { exact: true })).toBeVisible();
  await expect(page.locator(".answer-text")).toContainText("30 天");
  await expect(page.locator(".answer-text")).toContainText("15 天");
  await expect(page.locator(".evidence-card")).toHaveCount(2);
  await expect(page.locator(".clarification")).toBeVisible();
  await page.screenshot({
    path: "../examples/screenshots/conflict.png",
    fullPage: true,
  });
});

test("tool failure is explicit and library remains usable on mobile", async ({
  page,
}) => {
  await mockMode(page);
  await page.getByRole("button", { name: "评审用例", exact: true }).click();
  await page
    .locator(".scenario-card")
    .filter({
      has: page.getByRole("heading", { name: "检索工具失败", exact: true }),
    })
    .getByRole("button", { name: /运行场景/ })
    .click();
  await expect(page.getByText("尚未完成", { exact: true })).toBeVisible();
  await expect(page.locator(".answer-text")).toContainText("工具调用失败");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /查看查证过程/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("dialog").getByRole("link", { name: "下载完整 Trace" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "知识库", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每一条知识，都有出处" }),
  ).toBeVisible();
  await page.getByPlaceholder("搜索标题或文档 ID").fill("D03");
  await expect(page.locator(".document-card")).toHaveCount(1);
  await page.screenshot({
    path: "../examples/screenshots/mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

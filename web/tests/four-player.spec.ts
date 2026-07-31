import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

async function enter(page: Page, name: string) {
  await page.goto("/");
  await page.getByTestId("display-name").fill(name);
  await page.getByTestId("create-guest").click();
  await expect(page.getByRole("heading", { name: "Find your table" })).toBeVisible();
}

async function submitDeck(page: Page, seat: string, text: string) {
  const zimone = seat === "A" || seat === "C";
  await page.getByTestId("deck-name").fill(`Deck ${seat}`);
  await page
    .getByTestId("commander-name")
    .fill(zimone ? "Zimone and Dina" : "Mishra, Eminent One");
  await page.getByTestId("deck-list").fill(text);
  await page.getByTestId("submit-deck").click();
  await expect(page.getByText("Deck validated: trusted-only semantic gate passes.")).toBeVisible();
}

test("four isolated browser contexts play through authoritative mulligans and reconnect", async ({ browser }) => {
  const contexts: BrowserContext[] = [];
  const pages: Page[] = [];
  try {
    for (const seat of "ABCD") {
      const context = await browser.newContext();
      contexts.push(context);
      const page = await context.newPage();
      pages.push(page);
      await enter(page, `Browser ${seat}`);
    }

    await pages[0].getByTestId("create-room").click();
    const invite = await pages[0].getByTestId("room-invite").textContent();
    expect(invite).toBeTruthy();
    for (let index = 1; index < 4; index += 1) {
      await pages[index].getByTestId("invite-code").fill(invite!);
      await pages[index].getByTestId("seat-select").selectOption("ABCD"[index]);
      await pages[index].getByTestId("join-room").click();
      await expect(pages[index].getByTestId(`seat-${"ABCD"[index]}`)).toContainText(`Browser ${"ABCD"[index]}`);
    }

    const zimone = await readFile(path.resolve("..", "examples", "zimone-and-dina.txt"), "utf8");
    const mishra = await readFile(path.resolve("..", "examples", "mishra-eminent-one.txt"), "utf8");
    for (let index = 0; index < 4; index += 1) {
      const seat = "ABCD"[index];
      await submitDeck(pages[index], seat, seat === "A" || seat === "C" ? zimone : mishra);
    }

    await expect(pages[0].getByTestId("start-game")).toBeEnabled();
    await pages[0].getByTestId("start-game").click();
    for (const page of pages) {
      await expect(page.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
      await expect(page.getByTestId("decision-panel")).toBeVisible();
    }
    const handA = await pages[0].getByTestId("own-hand").textContent();
    const handB = await pages[1].getByTestId("own-hand").textContent();
    expect(handA).not.toEqual(handB);

    for (let index = 0; index < 4; index += 1) {
      await expect(pages[index].getByTestId("action-keep")).toBeVisible();
      await pages[index].getByTestId("action-keep").click();
    }

    await pages[0].reload();
    // Multiplayer Commander keeps the first-player draw, so A has eight after
    // all four keeps advance the engine into A's first draw step.
    await expect(pages[0].getByTestId("own-hand").locator(".hand-card")).toHaveCount(8);
    await expect(pages[0].getByText("LIVE", { exact: true })).toBeVisible();
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

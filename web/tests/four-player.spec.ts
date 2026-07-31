import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
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
  await expect(page.getByTestId("deck-ready-summary")).toContainText(`Deck ${seat}`);
}

async function viewRevision(page: Page): Promise<number> {
  return Number(await page.locator(".game-shell").getAttribute("data-view-revision"));
}

async function startFourPlayerGame(browser: Browser): Promise<{ contexts: BrowserContext[]; pages: Page[] }> {
  const contexts: BrowserContext[] = [];
  const pages: Page[] = [];
  for (const seat of "ABCD") {
    const context = await browser.newContext();
    contexts.push(context);
    const page = await context.newPage();
    pages.push(page);
    await enter(page, `Choices ${seat}`);
  }
  await pages[0].getByTestId("create-room").click();
  const invite = await pages[0].getByTestId("room-invite").textContent();
  expect(invite).toBeTruthy();
  for (let index = 1; index < 4; index += 1) {
    await pages[index].getByTestId("invite-code").fill(invite!);
    await pages[index].getByTestId("seat-select").selectOption("ABCD"[index]);
    await pages[index].getByTestId("join-room").click();
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
  return { contexts, pages };
}

async function submitImmediateAction(page: Page, actionId: string) {
  const revision = await viewRevision(page);
  await page.getByTestId(`action-${actionId}`).click();
  await expect.poll(() => viewRevision(page)).toBeGreaterThan(revision);
}

async function submitOpenChoice(page: Page) {
  const revision = await viewRevision(page);
  await page.getByTestId("submit-choice").click();
  await expect.poll(() => viewRevision(page)).toBeGreaterThan(revision);
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

    await expect(pages[0].getByTestId("room-invite")).toHaveText(invite!);
    await pages[0].getByTestId("replace-invite").click();
    await expect(pages[0].getByText("A new invite code was created.")).toBeVisible();
    const replacementInvite = await pages[0].getByTestId("room-invite").textContent();
    expect(replacementInvite).toBeTruthy();
    expect(replacementInvite).not.toEqual(invite);
    await pages[0].reload();
    await expect(pages[0].getByTestId("room-invite")).toHaveText(replacementInvite!);

    await pages[0].getByTestId("unready-deck").click();
    await expect(pages[0].getByTestId("submit-deck")).toBeVisible();
    await expect(pages[0].getByTestId("seat-A")).toContainText("WAITING");
    await expect(pages[0].getByTestId("start-game")).toBeDisabled();
    await submitDeck(pages[0], "A", zimone);

    await expect(pages[0].getByTestId("start-game")).toBeEnabled();
    await pages[0].getByTestId("start-game").click();
    for (const page of pages) {
      await expect(page.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
      await expect(page.getByTestId("decision-panel")).toBeVisible();
    }
    const handA = await pages[0].getByTestId("own-hand").textContent();
    const handB = await pages[1].getByTestId("own-hand").textContent();
    expect(handA).not.toEqual(handB);

    for (const page of pages) {
      await expect(page.getByTestId("game-status")).toHaveText("ACTIVE");
    }
    await expect(pages[0].getByTestId("stop-game")).toBeVisible();
    for (const member of pages.slice(1)) {
      await expect(member.getByTestId("stop-game")).toHaveCount(0);
    }
    await pages[1].getByTestId("inspect-game").click();
    await expect(pages[1].getByTestId("game-inspection")).toContainText("active");
    await pages[0].getByTestId("stop-reason").fill("Browser lifecycle regression");
    await pages[0].getByTestId("stop-game").click();
    for (const page of pages) {
      await expect(page.getByTestId("game-status")).toHaveText("PAUSED");
      await expect(page.getByTestId("paused-banner")).toContainText("Browser lifecycle regression");
    }
    await expect(pages[0].getByTestId("action-keep")).toBeDisabled();
    for (const waitingSeat of pages.slice(1)) {
      await expect(waitingSeat.locator('[data-testid^="action-"]')).toHaveCount(0);
      await expect(waitingSeat.getByTestId("decision-panel")).toContainText(
        "Waiting for another player’s decision.",
      );
    }
    await pages[1].reload();
    await expect(pages[1].getByText("LIVE", { exact: true })).toBeVisible();
    await expect(pages[1].getByTestId("game-status")).toHaveText("PAUSED");
    await expect(pages[0].getByTestId("resume-game")).toBeVisible();
    await pages[0].getByTestId("resume-game").click();
    for (const page of pages) {
      await expect(page.getByTestId("game-status")).toHaveText("ACTIVE");
      await expect(page.getByTestId("paused-banner")).toHaveCount(0);
    }

    for (let index = 0; index < 4; index += 1) {
      const revisions = await Promise.all(pages.map(viewRevision));
      await expect(pages[index].getByTestId("action-keep")).toBeVisible();
      if (index === 0) {
        let firstEnvelope: Record<string, unknown> | null = null;
        await pages[index].route("**/api/v1/games/*/commands", async (route) => {
          firstEnvelope = route.request().postDataJSON() as Record<string, unknown>;
          await route.abort("connectionfailed");
        }, { times: 1 });
        await pages[index].getByTestId("action-keep").click();
        await expect(pages[index].getByTestId("command-retry")).toBeVisible();
        const retriedRequest = pages[index].waitForRequest("**/api/v1/games/*/commands");
        await pages[index].getByRole("button", { name: "Retry exact command" }).click();
        const retriedEnvelope = (await retriedRequest).postDataJSON() as Record<string, unknown>;
        expect(retriedEnvelope.command_id).toEqual(firstEnvelope!.command_id);
        expect(retriedEnvelope).toEqual(firstEnvelope);
      } else {
        await pages[index].getByTestId("action-keep").click();
      }
      // A click only proves that the browser dispatched the command. Wait for
      // the authoritative HTTP receipt before allowing the next declaration
      // (or the reconnect below) to observe the resulting game state.
      await expect(pages[index].locator(".toast")).toContainText("Accepted keep");
      for (let seatIndex = 0; seatIndex < 4; seatIndex += 1) {
        await expect.poll(() => viewRevision(pages[seatIndex])).toBeGreaterThan(revisions[seatIndex]);
      }
    }

    // Depending on the seeded hands, the rules engine may pause for any
    // seat's meaningful upkeep response or skip pass-only windows. The
    // revision barriers above synchronize on the final declaration without
    // assuming a particular phase or priority holder.
    const projectedHandCount = await pages[0].getByTestId("own-hand").locator(".hand-card").count();
    const projectedDecision = await pages[0].getByTestId("decision-panel").textContent();
    await pages[0].reload();
    await expect(pages[0].getByText("LIVE", { exact: true })).toBeVisible();
    await expect(pages[0].getByTestId("own-hand").locator(".hand-card")).toHaveCount(projectedHandCount);
    await expect(pages[0].getByTestId("decision-panel")).toHaveText(projectedDecision!);
    await pages[0].setViewportSize({ width: 390, height: 844 });
    await expect(pages[0].getByTestId("decision-panel")).toBeVisible();
    await expect(pages[0].getByTestId("own-hand")).toBeVisible();
    expect(await pages[0].evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test("generic private choice form executes a penalized multiplayer mulligan", async ({ browser }) => {
  let contexts: BrowserContext[] = [];
  try {
    const started = await startFourPlayerGame(browser);
    contexts = started.contexts;
    const pages = started.pages;

    const mulliganTrigger = pages[0].getByTestId("action-mulligan");
    await mulliganTrigger.click();
    await expect(pages[0].getByTestId("choice-dialog")).toBeVisible();
    await pages[0].keyboard.press("Escape");
    await expect(pages[0].getByTestId("choice-dialog")).toHaveCount(0);
    await expect(mulliganTrigger).toBeFocused();
    await mulliganTrigger.click();
    await expect(pages[0].getByTestId("choice-dialog")).toBeVisible();
    await pages[0].getByTestId("choice-override_reason").fill("Browser choice-form coverage");
    await submitOpenChoice(pages[0]);

    for (let index = 1; index < 4; index += 1) {
      await expect(pages[index].getByTestId("action-keep")).toBeVisible();
      await submitImmediateAction(pages[index], "keep");
    }

    await expect(pages[0].getByTestId("action-mulligan")).toBeVisible();
    await pages[0].getByTestId("action-mulligan").click();
    await pages[0].getByTestId("choice-override_reason").fill("Deterministic browser regression coverage");
    await submitOpenChoice(pages[0]);

    await expect(pages[0].getByTestId("action-bottom")).toBeVisible();
    await pages[0].getByTestId("action-bottom").click();
    await expect(pages[0].getByTestId("choice-dialog")).toBeVisible();
    const firstCard = pages[0].locator('[data-testid^="choice-cards-"]').first();
    const testId = await firstCard.getAttribute("data-testid");
    expect(testId).toBeTruthy();
    await firstCard.check();
    for (const opponent of pages.slice(1)) {
      expect((await opponent.content()).includes(testId!)).toBeFalsy();
      await expect(opponent.getByTestId("choice-dialog")).toHaveCount(0);
    }
    await submitOpenChoice(pages[0]);

    await expect(pages[0].getByTestId("action-keep")).toBeVisible();
    await expect(pages[0].getByTestId("own-hand").locator(".hand-card")).toHaveCount(6);
    await submitImmediateAction(pages[0], "keep");
    // The engine may stop at a meaningful upkeep window or advance through
    // the opening draw, depending on the random hand. Either way, the bottom
    // operation above was observed authoritatively at six cards.
    expect([6, 7]).toContain(
      await pages[0].getByTestId("own-hand").locator(".hand-card").count(),
    );
    for (const opponent of pages.slice(1)) {
      await expect(opponent.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
    }
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

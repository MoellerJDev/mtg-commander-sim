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
  // These duplicated lists exercise the browser protocol, not matchup or
  // semantic-coverage evidence. A draft mechanic contract may correctly keep
  // the ready list behind a visible fail-closed fidelity warning.
  await expect(page.locator(".success-banner, .warning-banner").filter({ hasText: /Deck (validated|accepted)/ })).toBeVisible();
  await expect(page.getByTestId("deck-ready-summary")).toContainText(`Deck ${seat}`);
}

async function viewRevision(page: Page): Promise<number> {
  return Number(await page.locator(".game-shell").getAttribute("data-view-revision"));
}

async function expectCardSurface(page: Page, seat: string) {
  const firstCard = page.getByTestId("own-hand").locator(".hand-card").first();
  const name = await firstCard.locator(".card-copy strong").textContent();
  expect(name).toBeTruthy();
  await firstCard.hover();
  await expect(page.getByTestId("card-inspector")).toBeVisible();
  await expect(page.getByTestId("card-inspector")).toContainText(name!);
  await expect(page.getByTestId(`zone-${seat}-graveyard`)).toBeDisabled();
  await expect(page.getByTestId(`zone-${seat}-exile`)).toBeDisabled();
}

async function startFourPlayerGame(browser: Browser): Promise<{ contexts: BrowserContext[]; pages: Page[]; invite: string }> {
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
  for (let index = 0; index < pages.length; index += 1) {
    const page = pages[index];
    await expect(page.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
    await expect(page.getByTestId("decision-panel")).toBeVisible();
    await expectCardSurface(page, "ABCD"[index]);
  }
  return { contexts, pages, invite: invite! };
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

test("four shared-cookie browser tabs retain isolated seats through mulligans and reconnect", async ({ browser }) => {
  const contexts: BrowserContext[] = [];
  const pages: Page[] = [];
  try {
    // One context deliberately shares its cookie jar across all pages. The
    // application must still bind each tab to its own guest/seat session.
    const context = await browser.newContext();
    contexts.push(context);
    for (const seat of "ABCD") {
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
    await pages[1].reload();
    await pages[2].reload();
    await expect(pages[1].getByTestId("seat-B")).toHaveClass(/mine/);
    await expect(pages[2].getByTestId("seat-C")).toHaveClass(/mine/);

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
    for (let index = 0; index < pages.length; index += 1) {
      const page = pages[index];
      await expect(page.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
      await expect(page.getByTestId("decision-panel")).toBeVisible();
      await expectCardSurface(page, "ABCD"[index]);
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
    const mobileViewer = pages[0].getByRole("button", { name: /^View / });
    await expect(mobileViewer).toBeVisible();
    await mobileViewer.click();
    await expect(pages[0].getByTestId("card-inspector-expanded")).toBeVisible();
    await pages[0].keyboard.press("Escape");
    await expect(pages[0].getByTestId("card-inspector-expanded")).toHaveCount(0);
    expect(await pages[0].evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test("an invited spectator receives a read-only projection and complete public log", async ({ browser }) => {
  let playerContexts: BrowserContext[] = [];
  const spectatorContext = await browser.newContext();
  try {
    const started = await startFourPlayerGame(browser);
    playerContexts = started.contexts;
    const spectator = await spectatorContext.newPage();
    await enter(spectator, "Table spectator");
    await spectator.getByTestId("invite-code").fill(started.invite);
    await spectator.getByTestId("watch-room").click();

    await expect(spectator.getByTestId("watch-mode")).toBeVisible();
    await expect(spectator.locator(".player-board")).toHaveCount(4);
    await expect(spectator.getByTestId("own-hand")).toHaveCount(0);
    await expect(spectator.locator('[data-testid^="action-"]')).toHaveCount(0);
    await expect(spectator.getByTestId("decision-panel")).toContainText(
      "Watching the table",
    );

    await spectator.getByTestId("open-public-log").click();
    await expect(spectator.getByTestId("public-game-log")).toBeVisible();
    await expect(spectator.getByTestId("public-log-entry").first()).toBeVisible();
    const beforeLogCount = await spectator.getByTestId("public-log-entry").count();
    const beforeRevision = await viewRevision(spectator);

    await submitImmediateAction(started.pages[0], "keep");
    await expect.poll(() => viewRevision(spectator)).toBeGreaterThan(beforeRevision);
    await spectator.getByTestId("refresh-public-log").click();
    await expect.poll(async () => spectator.getByTestId("public-log-entry").count()).toBeGreaterThanOrEqual(beforeLogCount);

    await spectator.keyboard.press("Escape");
    await expect(spectator.getByTestId("public-game-log")).toHaveCount(0);
    await spectator.reload();
    await expect(spectator.getByTestId("watch-mode")).toBeVisible();
    await expect(spectator.getByTestId("own-hand")).toHaveCount(0);
    await spectator.getByTestId("open-public-log").click();
    await expect(spectator.getByTestId("public-log-entry").first()).toBeVisible();
  } finally {
    await spectatorContext.close();
    await Promise.all(playerContexts.map((context) => context.close()));
  }
});

test("a shared-cookie 1v1 lobby can replace rooms, remove a player, and start a duel", async ({ browser }) => {
  const context = await browser.newContext();
  const host = await context.newPage();
  const opponent = await context.newPage();
  try {
    await host.route(
      /\/api\/v1\/rooms(?:\/[^/]+\/replace)?$/,
      async (route) => {
        const request = route.request();
        const payload = request.postDataJSON() as Record<string, unknown>;
        await route.continue({
          postData: JSON.stringify({ ...payload, seed: 2 }),
          headers: {
            ...request.headers(),
            "content-type": "application/json",
          },
        });
      },
    );
    await enter(host, "Duel host");
    await enter(opponent, "Duel opponent");
    await host.getByTestId("room-size").selectOption("2");
    await host.getByTestId("create-room").click();
    await expect(host.getByTestId("seat-A")).toContainText("Duel host");
    await expect(host.getByTestId("seat-C")).toHaveCount(0);
    const staleInvite = await host.getByTestId("room-invite").textContent();
    expect(staleInvite).toBeTruthy();

    await opponent.getByTestId("invite-code").fill(staleInvite!);
    await opponent.getByTestId("seat-select").selectOption("B");
    await opponent.getByTestId("join-room").click();
    await expect(opponent.getByTestId("seat-B")).toContainText("Duel opponent");

    await host.getByTestId("new-room-size").selectOption("2");
    await host.getByTestId("new-room").click();
    await expect(host.getByTestId("room-invite")).not.toHaveText(staleInvite!);
    const invite = await host.getByTestId("room-invite").textContent();
    expect(invite).toBeTruthy();
    expect(invite).not.toEqual(staleInvite);
    await expect(opponent.getByRole("heading", { name: "Find your table" })).toBeVisible();

    await opponent.getByTestId("invite-code").fill(staleInvite!);
    await opponent.getByTestId("join-room").click();
    await expect(opponent.getByRole("alert")).toContainText("Invite code not found");
    await opponent.getByTestId("invite-code").fill(invite!);
    await opponent.getByTestId("join-room").click();
    await expect(opponent.getByTestId("seat-B")).toContainText("Duel opponent");

    await host.getByTestId("remove-seat-B").click();
    await expect(host.getByTestId("seat-B")).toContainText("Open seat");
    await expect(opponent.getByRole("heading", { name: "Find your table" })).toBeVisible();
    await opponent.getByTestId("invite-code").fill(invite!);
    await opponent.getByTestId("seat-select").selectOption("B");
    await opponent.getByTestId("join-room").click();

    const zimone = await readFile(path.resolve("..", "examples", "zimone-and-dina.txt"), "utf8");
    const mishra = await readFile(path.resolve("..", "examples", "mishra-eminent-one.txt"), "utf8");
    await submitDeck(host, "A", zimone);
    await submitDeck(opponent, "B", mishra);
    await expect(host.getByTestId("start-game")).toHaveText("Start duel");
    await expect(host.getByTestId("start-game")).toBeEnabled();
    await host.getByTestId("start-game").click();
    await expect(host.getByText("COMMANDER DUEL")).toBeVisible();
    await expect(opponent.getByText("COMMANDER DUEL")).toBeVisible();
    await expect(host.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
    await expect(opponent.getByTestId("own-hand").locator(".hand-card")).toHaveCount(7);
    await expect(host.locator(".player-board")).toHaveCount(2);
    await expect(opponent.locator(".player-board")).toHaveCount(2);

    await submitImmediateAction(host, "keep");
    await submitImmediateAction(opponent, "keep");
    const swamp = host
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: "Swamp" }) });
    await expect(swamp).toHaveCount(1);
    await expect(swamp).toHaveAttribute("draggable", "true");
    const beforeDrop = await viewRevision(host);
    await swamp.dragTo(host.getByTestId("own-battlefield"));
    await expect.poll(() => viewRevision(host)).toBeGreaterThan(beforeDrop);
    await expect(host.getByTestId("own-battlefield")).toContainText("Swamp");
    await expect(host.getByTestId("own-hand").locator(".hand-card")).toHaveCount(6);
  } finally {
    await context.close();
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

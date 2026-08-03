import { expect, test, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

async function enter(page: Page, name: string) {
  await page.goto("/");
  await page.getByTestId("display-name").fill(name);
  await page.getByTestId("create-guest").click();
  await expect(page.getByRole("heading", { name: "Find your table" })).toBeVisible();
}

async function submitNamedDeck(page: Page, name: string, commander: string, text: string) {
  await page.getByTestId("deck-name").fill(name);
  await page.getByTestId("commander-name").fill(commander);
  await page.getByTestId("deck-list").fill(text);
  await page.getByTestId("submit-deck").click();
  // These duplicated lists exercise the browser protocol, not matchup or
  // semantic-coverage evidence. A draft mechanic contract may correctly keep
  // the ready list behind a visible fail-closed fidelity warning.
  await expect(page.locator(".success-banner, .warning-banner").filter({ hasText: /Deck (validated|accepted)/ })).toBeVisible();
  await expect(page.getByTestId("deck-ready-summary")).toContainText(name);
}

async function submitDeck(page: Page, seat: string, text: string) {
  const zimone = seat === "A" || seat === "C";
  await submitNamedDeck(
    page,
    `Deck ${seat}`,
    zimone ? "Zimone and Dina" : "Mishra, Eminent One",
    text,
  );
}

async function viewRevision(page: Page): Promise<number> {
  return Number(await page.locator(".game-shell").getAttribute("data-view-revision"));
}

async function expectCardSurface(page: Page, seat: string) {
  const firstCard = page.getByTestId("own-hand").locator(".hand-card").first();
  const name = await firstCard.locator(".card-copy strong").textContent();
  expect(name).toBeTruthy();
  const visibleFaceName = name!.split(" // ", 1)[0];
  await firstCard.hover();
  await expect(page.getByTestId("card-inspector")).toBeVisible();
  await expect(page.getByTestId("card-inspector")).toContainText(visibleFaceName);
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

async function submitFormAction(page: Page, actionId: string) {
  await page.getByTestId(`action-${actionId}`).click();
  await expect(page.getByTestId("choice-dialog")).toBeVisible();
  await submitOpenChoice(page);
}

async function submitMaybeFormAction(page: Page, actionId: string, clickTimeout = 15_000) {
  const revision = await viewRevision(page);
  const dialog = page.getByTestId("choice-dialog");
  await page.getByTestId(`action-${actionId}`).click({ timeout: clickTimeout });
  await expect
    .poll(async () => (await dialog.isVisible()) || (await viewRevision(page)) > revision)
    .toBe(true);
  if (await dialog.isVisible()) {
    await submitOpenChoice(page);
  }
}

async function ensureFullControl(page: Page) {
  const toggle = page.getByTestId("auto-pass-toggle");
  if (await toggle.getAttribute("aria-pressed") === "true") {
    await toggle.click();
  }
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect(toggle).toContainText("Full control on");
}

async function actionIsReady(action: Locator): Promise<boolean> {
  // Priority can advance between the visibility and enabled checks. A vanished
  // capability is a normal projection transition, not a test failure.
  if (!(await action.isVisible())) return false;
  return action.isEnabled({ timeout: 250 }).catch(() => false);
}

async function passUntilDraggable(pages: readonly Page[], card: Locator) {
  for (let attempts = 0; attempts < 20; attempts += 1) {
    if (await card.getAttribute("draggable") === "true") return;
    await expect.poll(async () => {
      if (await card.getAttribute("draggable") === "true") return "ready";
      for (let index = 0; index < pages.length; index += 1) {
        const pass = pages[index].getByTestId("action-pass");
        if (await actionIsReady(pass)) return `pass-${index}`;
      }
      return "waiting";
    }, {
      // A Windows Game Record durability save may briefly keep the accepted
      // action disabled while its review artifacts are written. Wait for the
      // authoritative acknowledgement; never manufacture another pass.
      timeout: 45_000,
    }).not.toBe("waiting");
    if (await card.getAttribute("draggable") === "true") return;
    for (const page of pages) {
      const pass = page.getByTestId("action-pass");
      if (!(await actionIsReady(pass))) continue;
      try {
        await submitMaybeFormAction(page, "pass", 2_000);
      } catch (error) {
        // Safe Auto-pass may win the race for a response window. The next
        // iteration must still observe either the requested card or another
        // explicit server-issued pass before advancing the scripted game.
        if (await card.getAttribute("draggable") !== "true"
          && await actionIsReady(pass)) throw error;
      }
      break;
    }
  }
  await expect(card).toHaveAttribute("draggable", "true");
}

const browserTriggerDeck = `Commander:
1 Mishra, Eminent One

Mainboard:
1 Sunscorched Desert
1 Orcish Bowmasters
1 Sol Ring
32 Island
32 Swamp
32 Mountain
`;

const browserResponseDeck = `Commander:
1 Zimone and Dina

Mainboard:
1 An Offer You Can't Refuse
33 Island
33 Swamp
32 Forest
`;

const browserCombatDeck = `Commander:
1 Zimone and Dina

Mainboard:
33 Island
33 Swamp
33 Forest
`;

const browserCombatDefenderDeck = `Commander:
1 Mishra, Eminent One

Mainboard:
33 Island
33 Swamp
33 Mountain
`;

// This intentionally duplicated vanilla-commander list is a deterministic
// lifecycle witness. It proves natural browser completion, never matchup
// strength or broader Oracle coverage.
const browserNaturalWinnerDeck = `Commander:
1 Yargle and Multani

Mainboard:
50 Swamp
49 Forest
`;

test("@smoke four shared-cookie browser tabs retain isolated seats through mulligans and reconnect", async ({ browser }) => {
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
      await ensureFullControl(page);
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
    for (const pausedSeat of pages) {
      await expect(pausedSeat.locator('[data-testid^="action-"]')).toHaveCount(0);
      await expect(pausedSeat.getByTestId("paused-decision")).toContainText(
        "No player action or priority pass is pending",
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
  host.setDefaultTimeout(15_000);
  opponent.setDefaultTimeout(15_000);
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
    await expect(host.getByTestId("commander-damage-A")).toContainText("0");
    await expect(host.getByTestId("commander-damage-B")).toContainText("0");
    await expect(host.getByTestId("hand-panel")).toHaveAttribute("data-resizable", "true");
    expect(await host.getByTestId("hand-panel").evaluate((element) => {
      const style = getComputedStyle(element);
      return { position: style.position, resize: style.resize };
    })).toEqual({ position: "relative", resize: "vertical" });
    const dockBottomBefore = await host.getByTestId("table-bottom-dock").evaluate(
      (element) => Math.round(element.getBoundingClientRect().bottom),
    );
    await host.setViewportSize({ width: 1180, height: 760 });
    const viewportBottom = await host.evaluate(() => window.innerHeight);
    const dockBottomAfter = await host.getByTestId("table-bottom-dock").evaluate(
      (element) => Math.round(element.getBoundingClientRect().bottom),
    );
    expect(dockBottomAfter).toBe(viewportBottom - 8);
    expect(dockBottomAfter).not.toBe(dockBottomBefore);
    await expect(host.getByTestId("auto-pass-toggle")).toHaveAttribute("aria-pressed", "true");
    await expect(host.getByTestId("auto-mana-toggle")).toHaveAttribute("aria-pressed", "true");
    await host.getByTestId("auto-pass-toggle").click();
    await expect(host.getByTestId("auto-pass-toggle")).toContainText("Full control on");
    await expect(host.getByTestId("auto-pass-toggle")).toHaveAttribute("aria-pressed", "false");

    await submitImmediateAction(host, "keep");
    await submitImmediateAction(opponent, "keep");
    await expect(host.getByTestId("action-pass")).toBeVisible();
    await expect(host.getByTestId("decision-panel")).toContainText("Pass priority");
    await submitFormAction(host, "pass");
    const swamp = host
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: "Swamp" }) });
    await expect(swamp).toHaveCount(1);
    await passUntilDraggable([host, opponent], swamp);
    const beforeDrop = await viewRevision(host);
    await swamp.dragTo(host.getByTestId("own-battlefield"));
    await expect.poll(() => viewRevision(host)).toBeGreaterThan(beforeDrop);
    await expect(host.getByTestId("own-battlefield")).toContainText("Swamp");
    await expect(host.getByTestId("own-hand").locator(".hand-card")).toHaveCount(6);

    await host.getByTestId("action-concede").click();
    await expect(host.getByTestId("choice-dialog")).toContainText("Concede game");
    await expect(host.getByTestId("choice-confirm_concede")).toHaveValue("true");
    await host.getByTestId("cancel-choice").click();
    await expect(host.getByTestId("choice-dialog")).toHaveCount(0);
    await expect(host.getByTestId("game-status")).toHaveText("ACTIVE");

    await host.getByTestId("action-concede").click();
    await submitOpenChoice(host);
    for (const page of [host, opponent]) {
      await expect(page.getByTestId("game-status")).toHaveText("COMPLETE");
      await expect(page.getByTestId("game-over-banner")).toContainText("Seat B wins");
      await expect(page.getByTestId("complete-decision")).toContainText("Seat B won");
      await expect(page.locator('[data-testid^="action-"]')).toHaveCount(0);
    }
  } finally {
    await context.close().catch(() => undefined);
  }
});

test("a duel stabilizes land ETBs, permits a stack response, and resolves Bowmasters", async ({ browser }) => {
  const hostContext = await browser.newContext();
  const opponentContext = await browser.newContext();
  const host = await hostContext.newPage();
  const opponent = await opponentContext.newPage();
  try {
    await host.route(/\/api\/v1\/rooms$/, async (route) => {
      const request = route.request();
      const payload = request.postDataJSON() as Record<string, unknown>;
      await route.continue({
        postData: JSON.stringify({ ...payload, seed: 42897 }),
        headers: { ...request.headers(), "content-type": "application/json" },
      });
    });
    await enter(host, "Trigger host");
    await enter(opponent, "Response opponent");
    await host.getByTestId("room-size").selectOption("2");
    await host.getByTestId("create-room").click();
    const invite = await host.getByTestId("room-invite").textContent();
    expect(invite).toBeTruthy();
    await opponent.getByTestId("invite-code").fill(invite!);
    await opponent.getByTestId("seat-select").selectOption("B");
    await opponent.getByTestId("join-room").click();

    await submitNamedDeck(host, "Trigger regression", "Mishra, Eminent One", browserTriggerDeck);
    await submitNamedDeck(opponent, "Response regression", "Zimone and Dina", browserResponseDeck);
    await host.getByTestId("start-game").click();
    await submitImmediateAction(host, "keep");
    await submitImmediateAction(opponent, "keep");

    const desert = host
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: "Sunscorched Desert" }) });
    await expect(desert).toHaveAttribute("draggable", "true");
    const beforeDesert = await viewRevision(host);
    await desert.dragTo(host.getByTestId("own-battlefield"));
    await expect.poll(() => viewRevision(host)).toBeGreaterThan(beforeDesert);
    await expect(host.getByTestId("decision-panel")).toContainText("Semantic.Target");
    await host.getByTestId("action-choose").click();
    await expect(host.getByTestId("choice-dialog")).toContainText("Seat B");
    await host.getByTestId("choice-target-B").check();
    await submitOpenChoice(host);
    await expect(host.getByTestId("player-B").getByLabel("39 life")).toBeVisible();
    await expect(opponent.getByTestId("player-B").getByLabel("39 life")).toBeVisible();

    const island = opponent
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: opponent.locator(".card-copy strong", { hasText: /^Island$/ }) })
      .first();
    await passUntilDraggable([host, opponent], island);
    const beforeIsland = await viewRevision(opponent);
    await island.click();
    await opponent.getByTestId("selected-card-actions").getByRole("button", { name: /^Play Island$/ }).click();
    await expect.poll(() => viewRevision(opponent)).toBeGreaterThan(beforeIsland);
    const swamp = host
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: /^Swamp$/ }) })
      .first();
    await passUntilDraggable([host, opponent], swamp);
    const beforeSwamp = await viewRevision(host);
    await swamp.click();
    await host.getByTestId("selected-card-actions").getByRole("button", { name: /^Play Swamp$/ }).click();
    await expect.poll(() => viewRevision(host)).toBeGreaterThan(beforeSwamp);

    await host.getByTestId("auto-mana-toggle").click();
    await expect(host.getByTestId("auto-mana-toggle")).toContainText("Manual mana on");
    const battlefieldSwamp = host
      .getByTestId("player-A")
      .locator(".battlefield .table-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: /^Swamp$/ }) })
      .first();
    const beforeManualTap = await viewRevision(host);
    await battlefieldSwamp.click();
    await expect.poll(() => viewRevision(host)).toBeGreaterThan(beforeManualTap);
    await expect(battlefieldSwamp).toHaveAttribute("data-tapped", "true");
    await expect(host.getByTestId("player-A").locator(".zone-summary")).toContainText("B1");
    const beforeManualUndo = await viewRevision(host);
    await battlefieldSwamp.click();
    await expect.poll(() => viewRevision(host)).toBeGreaterThan(beforeManualUndo);
    await expect(battlefieldSwamp).toHaveAttribute("data-tapped", "false");
    await expect(host.getByTestId("player-A").locator(".zone-summary")).not.toContainText("B1");
    await host.getByTestId("auto-mana-toggle").click();
    await expect(host.getByTestId("auto-mana-toggle")).toContainText("Auto-mana on");

    const ring = host
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: "Sol Ring" }) });
    await expect(ring).toHaveAttribute("draggable", "true");
    await ring.dragTo(host.getByTestId("own-battlefield"));
    await expect(host.getByTestId("choice-dialog")).toContainText("Cast Sol Ring");
    await submitOpenChoice(host);
    await expect(opponent.locator(".stack-panel")).toContainText("Sol Ring");
    const hostTappedLand = host.getByTestId("player-A").locator(".battlefield .table-card.tapped");
    const opponentTappedLand = opponent.getByTestId("player-A").locator(".battlefield .table-card.tapped");
    await expect(hostTappedLand).toHaveCount(1);
    await expect(opponentTappedLand).toHaveCount(1);
    await expect(hostTappedLand).toHaveAttribute("data-tapped", "true");
    await expect(hostTappedLand.locator(".tapped-state")).toHaveText("TAPPED");
    await expect(opponentTappedLand.locator(".tapped-state")).toHaveText("TAPPED");
    expect(await hostTappedLand.evaluate((element) => getComputedStyle(element).transform)).not.toBe("none");

    const offer = opponent
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: opponent.locator(".card-copy strong", { hasText: "An Offer You Can't Refuse" }) });
    await expect(offer).toHaveAttribute("draggable", "true");
    await offer.dragTo(opponent.getByTestId("own-battlefield"));
    await expect(opponent.getByTestId("choice-dialog")).toContainText("Sol Ring");
    await opponent.locator('[data-testid^="choice-target-"]').first().check();
    await submitOpenChoice(opponent);

    const bowmasters = host
      .getByTestId("own-hand")
      .locator(".hand-card")
      .filter({ has: host.locator(".card-copy strong", { hasText: "Orcish Bowmasters" }) });
    await expect(bowmasters).toHaveAttribute("draggable", "true");
    await bowmasters.dragTo(host.getByTestId("own-battlefield"));
    await expect(host.getByTestId("choice-dialog")).toContainText("Cast Orcish Bowmasters");
    await submitOpenChoice(host);
    await expect(host.getByTestId("decision-panel")).toContainText("Semantic.Target");
    await host.getByTestId("action-choose").click();
    await host.getByTestId("choice-target-B").check();
    await submitOpenChoice(host);

    await expect(host.getByTestId("player-B").getByLabel("38 life")).toBeVisible();
    await expect(host.getByTestId("own-battlefield")).toContainText("Orcish Bowmasters");
    await expect(host.getByTestId("own-battlefield")).toContainText("Army");
    await expect(host.getByTestId("game-status")).toHaveText("ACTIVE");
    await expect(host.getByTestId("paused-banner")).toHaveCount(0);
  } finally {
    await Promise.all([hostContext.close(), opponentContext.close()]);
  }
});

test("a duel declares an attacker in the browser and applies commander combat damage", async ({ browser }) => {
  // This journey crosses several auto-pass windows and normally finishes near
  // the global 90-second limit on Windows. Preserve assertion-driven waits
  // while leaving enough time for context cleanup under serial suite load.
  test.setTimeout(180_000);
  const hostContext = await browser.newContext();
  const opponentContext = await browser.newContext();
  const host = await hostContext.newPage();
  const opponent = await opponentContext.newPage();
  try {
    await host.route(/\/api\/v1\/rooms$/, async (route) => {
      const request = route.request();
      const payload = request.postDataJSON() as Record<string, unknown>;
      await route.continue({
        postData: JSON.stringify({ ...payload, seed: 1 }),
        headers: { ...request.headers(), "content-type": "application/json" },
      });
    });
    await enter(host, "Combat host");
    await enter(opponent, "Combat defender");
    await host.getByTestId("room-size").selectOption("2");
    await host.getByTestId("create-room").click();
    const invite = await host.getByTestId("room-invite").textContent();
    expect(invite).toBeTruthy();
    await opponent.getByTestId("invite-code").fill(invite!);
    await opponent.getByTestId("seat-select").selectOption("B");
    await opponent.getByTestId("join-room").click();
    await submitNamedDeck(host, "Combat attacker", "Zimone and Dina", browserCombatDeck);
    await submitNamedDeck(opponent, "Combat defender", "Mishra, Eminent One", browserCombatDefenderDeck);
    await host.getByTestId("start-game").click();
    await submitImmediateAction(host, "keep");
    await submitImmediateAction(opponent, "keep");

    async function playLand(page: Page, name?: string) {
      const cards = page.getByTestId("own-hand").locator(".hand-card");
      const land = name
        ? cards.filter({ has: page.locator(".card-copy strong", { hasText: new RegExp(`^${name}$`) }) }).first()
        : cards.first();
      await passUntilDraggable([host, opponent], land);
      const revision = await viewRevision(page);
      await land.dragTo(page.getByTestId("own-battlefield"));
      await expect.poll(() => viewRevision(page)).toBeGreaterThan(revision);
    }

    await playLand(host, "Forest");
    await playLand(opponent);
    await playLand(host, "Swamp");
    await playLand(opponent);
    await playLand(host, "Island");

    const commander = host
      .getByTestId("player-A")
      .locator(".command-zone .card-tile")
      .filter({ has: host.locator(".card-copy strong", { hasText: "Zimone and Dina" }) });
    await expect(commander).toHaveAttribute("draggable", "true");
    await commander.dragTo(host.getByTestId("own-battlefield"));
    await expect(host.getByTestId("choice-dialog")).toContainText("Cast Zimone and Dina");
    await submitOpenChoice(host);
    await expect(host.getByTestId("own-battlefield")).toContainText("Zimone and Dina");

    await playLand(opponent);
    await playLand(host);

    await submitFormAction(host, "pass");
    await expect(host.getByTestId("decision-panel")).toContainText("Combat.Attackers");
    await host.getByTestId("action-attack").click();
    const attackerChoice = host.locator('[data-testid^="choice-attackers-"]').first();
    await expect(attackerChoice).toBeVisible();
    await attackerChoice.selectOption("B");
    await submitOpenChoice(host);

    await expect(host.getByTestId("player-B").getByLabel("37 life")).toBeVisible();
    await expect(opponent.getByTestId("player-B").getByLabel("37 life")).toBeVisible();
    await host.getByTestId("open-public-log").click();
    await expect(host.getByTestId("public-game-log")).toContainText("attacked with 1 creature");
    await expect(host.getByTestId("public-game-log")).toContainText("Combat damage was dealt");
  } finally {
    await Promise.all([hostContext.close(), opponentContext.close()]);
  }
});

test("a trusted browser duel reaches a natural commander-damage winner", async ({ browser }) => {
  // This intentionally natural game persists more than one hundred real
  // commands. It completes near five minutes alone and can take longer after
  // the preceding serial journeys, especially on Windows or hosted CI.
  test.setTimeout(480_000);
  const hostContext = await browser.newContext();
  const opponentContext = await browser.newContext();
  const host = await hostContext.newPage();
  const opponent = await opponentContext.newPage();
  try {
    await host.route(/\/api\/v1\/rooms$/, async (route) => {
      const request = route.request();
      const payload = request.postDataJSON() as Record<string, unknown>;
      await route.continue({
        postData: JSON.stringify({ ...payload, seed: 1 }),
        headers: { ...request.headers(), "content-type": "application/json" },
      });
    });
    await enter(host, "Natural winner host");
    await enter(opponent, "Natural winner defender");
    await host.getByTestId("room-size").selectOption("2");
    await host.getByTestId("create-room").click();
    const invite = await host.getByTestId("room-invite").textContent();
    expect(invite).toBeTruthy();
    await opponent.getByTestId("invite-code").fill(invite!);
    await opponent.getByTestId("seat-select").selectOption("B");
    await opponent.getByTestId("join-room").click();
    await submitNamedDeck(host, "Natural winner A", "Yargle and Multani", browserNaturalWinnerDeck);
    await submitNamedDeck(opponent, "Natural winner B", "Yargle and Multani", browserNaturalWinnerDeck);
    await host.getByTestId("start-game").click();
    await submitImmediateAction(host, "keep");
    await submitImmediateAction(opponent, "keep");

    async function playLand(page: Page, name?: "Swamp" | "Forest") {
      const cards = page.getByTestId("own-hand").locator(".hand-card");
      const land = name
        ? cards.filter({ has: page.locator(".card-copy strong", { hasText: new RegExp(`^${name}$`) }) }).first()
        : cards.first();
      await passUntilDraggable([host, opponent], land);
      const revision = await viewRevision(page);
      await land.dragTo(page.getByTestId("own-battlefield"));
      await expect.poll(() => viewRevision(page)).toBeGreaterThan(revision);
    }

    async function declineCommanderDevelopment(page: Page) {
      // Once six mana is available, commander casting remains meaningful in
      // both main phases. Auto-pass must stop; this scripted witness declines
      // those two verified opportunities explicitly.
      await submitFormAction(page, "pass");
      await submitFormAction(page, "pass");
    }

    const requiredMana: Array<"Swamp" | "Forest"> = [
      "Swamp", "Swamp", "Forest", "Forest", "Swamp", "Forest",
    ];
    for (let turn = 0; turn < requiredMana.length; turn += 1) {
      await playLand(host, requiredMana[turn]);
      if (turn === requiredMana.length - 1) {
        const commander = host
          .getByTestId("player-A")
          .locator(".command-zone .card-tile")
          .filter({ has: host.locator(".card-copy strong", { hasText: "Yargle and Multani" }) });
        await expect(commander).toHaveAttribute("draggable", "true");
        await commander.dragTo(host.getByTestId("own-battlefield"));
        await expect(host.getByTestId("choice-dialog")).toContainText("Cast Yargle and Multani");
        await submitOpenChoice(host);
        await expect(host.getByTestId("own-battlefield")).toContainText("Yargle and Multani");
      }
      await playLand(opponent);
      if (turn === requiredMana.length - 1) {
        await declineCommanderDevelopment(opponent);
      }
    }

    async function attackWithCommander() {
      // A still has a legal land play, so advancing to combat is meaningful
      // and must not be consumed by Auto-pass.
      // Depending on the exact priority handoff, the first visible pass may be
      // an immediate priority action rather than the form-backed main-phase
      // pass. Advance through only those passes until attackers are requested.
      for (let attempt = 0; attempt < 8; attempt += 1) {
        const panel = host.getByTestId("decision-panel");
        const pass = host.getByTestId("action-pass");
        await expect
          .poll(async () => {
            if ((await panel.textContent())?.includes("Combat.Attackers")) {
              return "attackers";
            }
            return (await pass.isVisible()) && (await pass.isEnabled()) ? "pass" : "waiting";
          })
          .not.toBe("waiting");
        if ((await panel.textContent())?.includes("Combat.Attackers")) {
          break;
        }
        try {
          await submitMaybeFormAction(host, "pass", 2_000);
        } catch (error) {
          // A projection or the safe auto-pass effect may consume the enabled
          // pass between the poll and click. Wait for that in-flight command
          // to reveal either the attackers window or the next manual pass.
          await expect
            .poll(async () => {
              if ((await panel.textContent())?.includes("Combat.Attackers")) {
                return "attackers";
              }
              return (await pass.isVisible()) && (await pass.isEnabled()) ? "pass" : "waiting";
            })
            .not.toBe("waiting");
          if ((await panel.textContent())?.includes("Combat.Attackers")) {
            break;
          }
          if (!(await pass.isEnabled())) throw error;
        }
      }
      await expect(host.getByTestId("decision-panel")).toContainText("Combat.Attackers");
      await host.getByTestId("action-attack").click();
      const attackerChoice = host.locator('[data-testid^="choice-attackers-"]').first();
      await expect(attackerChoice).toBeVisible();
      await attackerChoice.selectOption("B");
      await submitOpenChoice(host);
    }

    await attackWithCommander();
    for (const page of [host, opponent]) {
      await expect(page.getByTestId("player-B").getByLabel("22 life")).toBeVisible();
      await expect(page.getByTestId("commander-damage-B")).toContainText("18 from Yargle and Multani");
    }
    await submitFormAction(host, "pass");
    await playLand(opponent);
    await declineCommanderDevelopment(opponent);

    await attackWithCommander();
    for (const page of [host, opponent]) {
      await expect(page.getByTestId("game-status")).toHaveText("COMPLETE");
      await expect(page.getByTestId("game-over-banner")).toContainText("Seat A wins");
      await expect(page.getByTestId("complete-decision")).toContainText("Seat A won");
      await expect(page.locator('[data-testid^="action-"]')).toHaveCount(0);
    }
    await host.getByTestId("open-public-log").click();
    await expect(host.getByTestId("public-game-log")).toContainText("B left the game: state-based loss");
    await expect(host.getByTestId("public-game-log")).toContainText("A won the game");
  } finally {
    await Promise.all([hostContext.close(), opponentContext.close()]);
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

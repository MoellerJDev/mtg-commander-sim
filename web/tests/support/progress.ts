import { type Page, type TestInfo } from "@playwright/test";

type ServerProgress = {
  processing_kind?: string | null;
  queue_depth?: number;
  persistence?: {
    pending?: boolean;
    pending_seconds?: number | null;
    last_total_seconds?: number | null;
    last_authoritative_seconds?: number | null;
    last_derived_review_seconds?: number | null;
  };
};

export type BrowserProgress = {
  page: number;
  gameId: string | null;
  viewRevision: number | null;
  stateRevision: number | null;
  commandCount: number | null;
  eventCount: number | null;
  lifecycle: string | null;
  phase: string | null;
  step: string | null;
  activePlayer: string | null;
  priorityPlayer: string | null;
  decisionId: string | null;
  latestEventId: string | null;
  latestEventCode: string | null;
  server: ServerProgress | null;
};

const submittedPassDecision = new WeakMap<Page, string>();

function numeric(value: string | undefined): number | null {
  if (value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function viewRevision(page: Page): Promise<number> {
  return Number(
    await page.locator(".game-shell").getAttribute("data-view-revision"),
  );
}

async function currentDecisionId(page: Page): Promise<string | null> {
  // A terminal projection correctly has no decision panel. `getAttribute`
  // auto-waits for a matching element and would turn metrics collection into
  // a suite-length timeout, so query the current zero-or-one element set
  // without waiting for a decision to reappear.
  const values = await page
    .getByTestId("decision-panel")
    .evaluateAll((elements) =>
      elements.map((element) => element.getAttribute("data-decision-id")),
    );
  return values[0] || null;
}

async function actionIsReady(page: Page): Promise<boolean> {
  const action = page.getByTestId("action-pass");
  if (!(await action.isVisible().catch(() => false))) return false;
  return action.isEnabled({ timeout: 250 }).catch(() => false);
}

export async function submitAuthorizedPass(
  page: Page,
): Promise<"submitted" | "raced" | "unavailable"> {
  const decisionId = await currentDecisionId(page);
  if (
    !decisionId ||
    submittedPassDecision.get(page) === decisionId ||
    !(await actionIsReady(page))
  ) {
    return "unavailable";
  }

  const revision = await viewRevision(page);
  try {
    await page.getByTestId("action-pass").click({ timeout: 2_000 });
    const dialog = page.getByTestId("choice-dialog");
    const transitionDeadline = Date.now() + 2_000;
    while (Date.now() < transitionDeadline) {
      if (await dialog.isVisible().catch(() => false)) {
        await page.getByTestId("submit-choice").click({ timeout: 2_000 });
        submittedPassDecision.set(page, decisionId);
        return "submitted";
      }
      if (
        (await viewRevision(page)) > revision ||
        !(await actionIsReady(page))
      ) {
        submittedPassDecision.set(page, decisionId);
        return "submitted";
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error("Pass click produced neither a choice nor state progress");
  } catch (error) {
    if (await actionIsReady(page)) throw error;
    if ((await viewRevision(page)) > revision) {
      submittedPassDecision.set(page, decisionId);
      return "submitted";
    }
    return "raced";
  }
}

async function serverProgress(
  page: Page,
  gameId: string,
): Promise<ServerProgress | null> {
  return page.evaluate(async (id) => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 2_000);
    try {
      const response = await fetch(`/api/v1/games/${id}/progress`, {
        credentials: "same-origin",
        signal: controller.signal,
      });
      return response.ok ? ((await response.json()) as ServerProgress) : null;
    } catch {
      return null;
    } finally {
      window.clearTimeout(timeout);
    }
  }, gameId);
}

export async function captureProgress(
  pages: readonly Page[],
): Promise<BrowserProgress[]> {
  return Promise.all(
    pages.map(async (page, index) => {
      const shell = page.locator(".game-shell");
      if ((await shell.count()) === 0) {
        return {
          page: index,
          gameId: null,
          viewRevision: null,
          stateRevision: null,
          commandCount: null,
          eventCount: null,
          lifecycle: null,
          phase: null,
          step: null,
          activePlayer: null,
          priorityPlayer: null,
          decisionId: null,
          latestEventId: null,
          latestEventCode: null,
          server: null,
        };
      }
      const data = await shell.evaluate((element) => ({
        ...((element as HTMLElement).dataset || {}),
      }));
      const gameId = data.gameId || null;
      return {
        page: index,
        gameId,
        viewRevision: numeric(data.viewRevision),
        stateRevision: numeric(data.stateRevision),
        commandCount: numeric(data.commandCount),
        eventCount: numeric(data.eventCount),
        lifecycle: data.lifecycleStatus || null,
        phase: data.phase || null,
        step: data.step || null,
        activePlayer: data.activePlayer || null,
        priorityPlayer: data.priorityPlayer || null,
        decisionId: await currentDecisionId(page),
        latestEventId: data.latestEventId || null,
        latestEventCode: data.latestEventCode || null,
        server: gameId ? await serverProgress(page, gameId) : null,
      };
    }),
  );
}

function canonicalProgress(progress: readonly BrowserProgress[]): string {
  return JSON.stringify(
    progress.map((entry) => ({
      page: entry.page,
      gameId: entry.gameId,
      viewRevision: entry.viewRevision,
      stateRevision: entry.stateRevision,
      commandCount: entry.commandCount,
      eventCount: entry.eventCount,
      lifecycle: entry.lifecycle,
      phase: entry.phase,
      step: entry.step,
      activePlayer: entry.activePlayer,
      priorityPlayer: entry.priorityPlayer,
      decisionId: entry.decisionId,
      latestEventId: entry.latestEventId,
      latestEventCode: entry.latestEventCode,
      processingKind: entry.server?.processing_kind ?? null,
      queueDepth: entry.server?.queue_depth ?? null,
      persistencePending: entry.server?.persistence?.pending ?? null,
      lastPersistence: entry.server?.persistence?.last_total_seconds ?? null,
    })),
  );
}

function rerunCommand(testInfo: TestInfo): string {
  const title = testInfo.title.replaceAll('"', '\\"');
  const group = process.env.MTG_BROWSER_GROUP || "focused";
  return `MTG_BROWSER_GROUP=${group} npx playwright test --grep "${title}" --workers=1`;
}

export async function driveUntil(
  pages: readonly Page[],
  goal: () => Promise<boolean>,
  testInfo: TestInfo,
  options: {
    label: string;
    noProgressMs?: number;
    overallMs?: number;
    advance?: () => Promise<boolean>;
  },
): Promise<void> {
  const noProgressMs = options.noProgressMs ?? 90_000;
  const overallMs = options.overallMs ?? 12 * 60_000;
  const started = Date.now();
  let lastProgressAt = started;
  let progress = await captureProgress(pages);
  let progressKey = canonicalProgress(progress);

  while (!(await goal())) {
    let submitted = options.advance ? await options.advance() : false;
    if (!submitted) {
      for (const page of pages) {
        const result = await submitAuthorizedPass(page);
        if (result !== "unavailable") {
          submitted = true;
          break;
        }
      }
    }
    if (!submitted) await new Promise((resolve) => setTimeout(resolve, 300));

    progress = await captureProgress(pages);
    const nextKey = canonicalProgress(progress);
    if (nextKey !== progressKey) {
      progressKey = nextKey;
      lastProgressAt = Date.now();
    }

    const now = Date.now();
    if (now - lastProgressAt >= noProgressMs || now - started >= overallMs) {
      const reason =
        now - lastProgressAt >= noProgressMs
          ? `no progress for ${noProgressMs}ms`
          : `overall deadline ${overallMs}ms exceeded`;
      throw new Error(
        `${options.label}: ${reason}\n${JSON.stringify(
          {
            elapsedMs: now - started,
            noProgressMs: now - lastProgressAt,
            pages: progress,
            rerun: rerunCommand(testInfo),
          },
          null,
          2,
        )}`,
      );
    }
  }
}

export async function annotateJourneyMetrics(
  pages: readonly Page[],
  contextCount: number,
  testInfo: TestInfo,
): Promise<void> {
  const progress = await captureProgress(pages).catch(() => []);
  const values = progress.filter((entry) => entry.gameId !== null);
  const maximum = (
    selector: (entry: BrowserProgress) => number | null | undefined,
  ): number | null => {
    const selected = values
      .map(selector)
      .filter((value): value is number => typeof value === "number");
    return selected.length ? Math.max(...selected) : null;
  };
  testInfo.annotations.push({
    type: "commander-journey-metrics",
    description: JSON.stringify({
      browser_contexts: contextCount,
      accepted_commands: maximum((entry) => entry.commandCount),
      authoritative_revisions: maximum((entry) => entry.stateRevision),
      projected_revisions: maximum((entry) => entry.viewRevision),
      persistence_seconds: maximum(
        (entry) => entry.server?.persistence?.last_total_seconds,
      ),
      authoritative_persistence_seconds: maximum(
        (entry) => entry.server?.persistence?.last_authoritative_seconds,
      ),
      derived_review_seconds: maximum(
        (entry) => entry.server?.persistence?.last_derived_review_seconds,
      ),
    }),
  });
}

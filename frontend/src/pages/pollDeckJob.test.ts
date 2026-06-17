import type { DeckJobStatus } from "../types";
import { DeckJobCancelledError, pollDeckJob } from "./pollDeckJob";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
  }
}

async function assertRejects(promise: Promise<unknown>, expectedMessage: string): Promise<void> {
  let thrown: unknown;
  try {
    await promise;
  } catch (e) {
    thrown = e;
  }
  if (!(thrown instanceof Error)) {
    throw new Error(`Expected Error("${expectedMessage}"), nothing was thrown`);
  }
  if (thrown.message !== expectedMessage) {
    throw new Error(`Expected Error("${expectedMessage}"), received Error("${thrown.message}")`);
  }
}

async function assertRejectsInstance<T extends Error>(
  promise: Promise<unknown>,
  ctor: new (...args: never[]) => T,
): Promise<void> {
  let thrown: unknown;
  try {
    await promise;
  } catch (e) {
    thrown = e;
  }
  if (!(thrown instanceof ctor)) {
    throw new Error(`Expected ${ctor.name}, received ${String(thrown)}`);
  }
}

function job(partial: Partial<DeckJobStatus> & Pick<DeckJobStatus, "status">): DeckJobStatus {
  return {
    job_id: "job-1",
    deck_id: null,
    error: null,
    status_code: null,
    ...partial,
  };
}

async function main(): Promise<void> {
  // resolves immediately when first poll is "done"
  {
    const result = await pollDeckJob(
      async () => job({ status: "done", deck_id: "deck-abc" }),
      "job-1",
      { sleep: async () => {} },
    );
    assertEqual(result, job({ status: "done", deck_id: "deck-abc" }));
  }

  // resolves after 2 "running" polls then "done"; getJob called exactly 3 times
  {
    let calls = 0;
    const result = await pollDeckJob(
      async () => {
        calls += 1;
        if (calls < 3) return job({ status: "running" });
        return job({ status: "done", deck_id: "deck-xyz" });
      },
      "job-1",
      { sleep: async () => {} },
    );
    assertEqual(calls, 3);
    assertEqual(result.status, "done");
    assertEqual(result.deck_id, "deck-xyz");
  }

  // throws with the job's error message when status is "error"
  {
    await assertRejects(
      pollDeckJob(
        async () => job({ status: "error", error: "Genie failed" }),
        "job-1",
        { sleep: async () => {} },
      ),
      "Genie failed",
    );
  }

  // throws "Generation timed out" when getJob always returns "running"
  {
    await assertRejects(
      pollDeckJob(async () => job({ status: "running" }), "job-1", {
        intervalMs: 100,
        timeoutMs: 100,
        sleep: async () => {},
      }),
      "Generation timed out",
    );
  }

  // throws DeckJobCancelledError when shouldStop returns true
  {
    await assertRejectsInstance(
      pollDeckJob(async () => job({ status: "running" }), "job-1", {
        sleep: async () => {},
        shouldStop: () => true,
      }),
      DeckJobCancelledError,
    );
  }

  // generic: resolves with a non-deck job shape (outline)
  {
    type OutlineJob = { status: "running" | "done" | "error"; slides?: { title: string }[] };
    const outlineJob = (partial: Partial<OutlineJob> & Pick<OutlineJob, "status">): OutlineJob => ({
      slides: [],
      ...partial,
    });
    const result = await pollDeckJob(
      async () => outlineJob({ status: "done", slides: [{ title: "Intro" }] }),
      "outline-job-1",
      { sleep: async () => {} },
    );
    assertEqual(result.slides, [{ title: "Intro" }]);
  }
}

main().then(() => {
  console.log("All assertions passed");
});

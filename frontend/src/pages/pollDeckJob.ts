export interface PollDeckJobOptions {
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
  shouldStop?: () => boolean;
}

export class DeckJobCancelledError extends Error {}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export async function pollDeckJob<
  T extends { status: "running" | "done" | "error"; error?: string | null },
>(
  getJob: (jobId: string) => Promise<T>,
  jobId: string,
  opts?: PollDeckJobOptions,
): Promise<T> {
  const intervalMs = opts?.intervalMs ?? 3000;
  const timeoutMs = opts?.timeoutMs ?? 600000;
  const sleep = opts?.sleep ?? defaultSleep;
  const maxPolls = Math.max(1, Math.ceil(timeoutMs / intervalMs));

  for (let poll = 0; poll < maxPolls; poll += 1) {
    const job = await getJob(jobId);
    if (job.status === "done") {
      return job;
    }
    if (job.status === "error") {
      throw new Error(job.error || "Generation failed");
    }
    if (poll + 1 >= maxPolls) {
      throw new Error("Generation timed out");
    }
    if (opts?.shouldStop?.()) {
      throw new DeckJobCancelledError();
    }
    await sleep(intervalMs);
  }

  throw new Error("Generation timed out");
}

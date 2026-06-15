import { Fragment } from "react";

export type ProgressIndicatorProps = {
  step: number;
  steps: string[];
};

export function ProgressIndicator({ step, steps }: ProgressIndicatorProps) {
  const last = Math.max(0, steps.length - 1);
  const safe = Math.min(Math.max(0, step), last);

  return (
    <div role="status" aria-live="polite" aria-label="Generation progress" className="progress-indicator">
      <div className="progress-indicator__row">
        {steps.map((label, i) => {
          const done = i < safe;
          const active = i === safe;
          const lineDone = i > 0 && i - 1 < safe;
          return (
            <Fragment key={label}>
              {i > 0 ? (
                <span
                  className={
                    "progress-indicator__line" + (lineDone ? " progress-indicator__line--done" : "")
                  }
                  aria-hidden
                />
              ) : null}
              <span
                className={
                  "progress-indicator__pill" +
                  (active ? " progress-indicator__pill--active" : "") +
                  (done ? " progress-indicator__pill--done" : "") +
                  (!done && !active ? " progress-indicator__pill--pending" : "")
                }
                aria-current={active ? "step" : undefined}
              >
                {label}
              </span>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

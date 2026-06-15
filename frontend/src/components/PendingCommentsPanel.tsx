import type { PendingComment } from "../types";

export type PendingCommentsPanelProps = {
  comments: PendingComment[];
  busy?: boolean;
  onApply: (id: string) => void | Promise<void>;
  onDiscard: (id: string) => void | Promise<void>;
  onApplyAll: () => void | Promise<void>;
};

export function PendingCommentsPanel(p: PendingCommentsPanelProps) {
  const busy = !!p.busy;
  return (
    <aside className="rail rail--right" aria-label="Pending comments">
      <div className="rail__title">
        <strong>Pending ({p.comments.length})</strong>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => p.onApplyAll()}
          disabled={busy || !p.comments.length}
          aria-busy={busy}
        >
          {busy ? "Applying…" : "Apply all"}
        </button>
      </div>

      {p.comments.map((c) => (
        <div key={c.id} className="comment-card">
          <div className="comment-card__target">{c.target_id}</div>
          <p className="comment-card__note">{c.note}</p>
          <div className="comment-card__actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => p.onApply(c.id)}
              disabled={busy}
              aria-busy={busy}
            >
              {busy ? "…" : "Apply"}
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => {
                if (!window.confirm("Discard this pending comment?")) return;
                void p.onDiscard(c.id);
              }}
              disabled={busy}
            >
              Discard
            </button>
          </div>
        </div>
      ))}

      {!p.comments.length && (
        <div className="empty-state pending-comments-empty" role="status">
          <p>Click any element on the deck to add a comment.</p>
        </div>
      )}
    </aside>
  );
}

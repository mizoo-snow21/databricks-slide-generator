import { useEffect, useRef, useState } from "react";

type Pos = { x: number; y: number };

export type InspectorPopoverProps = {
  pos: Pos;
  onSave: (note: string) => void | Promise<void>;
  onCancel: () => void;
};

export function InspectorPopover({ pos, onSave, onCancel }: InspectorPopoverProps) {
  const previouslyFocused = useRef<HTMLElement | null>(null);
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, []);

  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!saving) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, [saving]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="popover-title"
      className="popover"
      data-state="open"
      style={{ left: pos.x, top: pos.y }}
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
      }}
    >
      <div id="popover-title" className="mono popover__title">
        Comment on element
      </div>
      <textarea
        aria-labelledby="popover-title"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="e.g., make the title bolder and use the accent color (applies immediately)"
        autoFocus
      />
      <div className="popover__actions">
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={!note.trim() || saving}
          onClick={async () => {
            setSaving(true);
            try {
              await onSave(note);
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? (
            <>
              <span className="spinner" /> Saving… ({elapsed}s)
            </>
          ) : (
            "Save comment"
          )}
        </button>
      </div>
    </div>
  );
}

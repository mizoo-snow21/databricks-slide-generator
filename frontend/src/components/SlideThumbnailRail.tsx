import { memo, useMemo, useState } from "react";

export type SlideRef = { slide_id: string; outerHTML: string; title?: string };

export type SlideThumbnailRailProps = {
  slides: SlideRef[];
  deckStyles: string;
  activeSlideId: string | null;
  onSelect: (slideId: string) => void;
  onAdd: (prompt: string) => void | Promise<void>;
  onDelete: (slideId: string) => void | Promise<void>;
  onRegenerate: (slideId: string, feedback?: string) => void | Promise<void>;
};

const THUMB_W = 188;
const SCALE = THUMB_W / 1920;

export function SlideThumbnailRail(p: SlideThumbnailRailProps) {
  const [adding, setAdding] = useState(false);
  const [addPrompt, setAddPrompt] = useState("");

  return (
    <aside className="rail" aria-label="Slides">
      <div className="rail__title">
        <strong>Slides ({p.slides.length})</strong>
      </div>
      {p.slides.map((s, i) => (
        <ThumbCard
          key={s.slide_id}
          index={i}
          slide={s}
          deckStyles={p.deckStyles}
          active={s.slide_id === p.activeSlideId}
          onSelect={p.onSelect}
          onDelete={p.onDelete}
          onRegenerate={p.onRegenerate}
        />
      ))}

      {adding ? (
        <div style={{ marginTop: 12 }}>
          <textarea
            autoFocus
            aria-label="New slide prompt"
            className="textarea"
            name="addSlidePrompt"
            value={addPrompt}
            onChange={(e) => setAddPrompt(e.target.value)}
            placeholder="A one-line description of the new slide"
            rows={3}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={async () => {
                if (!addPrompt.trim()) return;
                await p.onAdd(addPrompt);
                setAdding(false);
                setAddPrompt("");
              }}
            >
              Add
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => {
                setAdding(false);
                setAddPrompt("");
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="btn btn--ghost btn--sm rail__add-slide"
          onClick={() => setAdding(true)}
        >
          <span className="rail__add-plus" aria-hidden>
            +
          </span>
          <span>Add slide</span>
        </button>
      )}
    </aside>
  );
}

const ThumbCard = memo(function ThumbCard(props: {
  index: number;
  slide: SlideRef;
  deckStyles: string;
  active: boolean;
  onSelect: (slideId: string) => void;
  onDelete: (slideId: string) => void;
  onRegenerate: (slideId: string, feedback?: string) => void | Promise<void>;
}) {
  const { index, slide, deckStyles, active, onSelect, onDelete, onRegenerate } = props;
  const srcDoc = useMemo(() => {
    const style = deckStyles
      ? `<style>body{margin:0;background:transparent}${deckStyles}</style>`
      : "";
    return `<!doctype html><html><head><meta charset="utf-8">${style}</head><body>${slide.outerHTML}</body></html>`;
  }, [deckStyles, slide.outerHTML]);

  return (
    <div className={`thumb${active ? " thumb--active" : ""}`}>
      <iframe
        sandbox=""
        srcDoc={srcDoc}
        className="thumb__preview"
        aria-hidden={true}
        style={{ transform: `scale(${SCALE})`, border: 0 }}
      />
      <button
        type="button"
        className="thumb__select"
        onClick={() => onSelect(slide.slide_id)}
        aria-label={`Slide ${index + 1}${slide.title ? ": " + slide.title : ""}`}
        aria-current={active ? "true" : undefined}
      />
      <span className="thumb__index" aria-hidden>
        {String(index + 1).padStart(2, "0")}
      </span>
      {slide.title && (
        <span className="thumb__title" aria-hidden>
          {slide.title}
        </span>
      )}
      <button
        type="button"
        className="thumb__regenerate"
        aria-label={`Regenerate slide ${index + 1}`}
        onClick={(e) => {
          e.stopPropagation();
          const fb = window.prompt(
            "How should this slide be different? (optional — leave blank for a fresh take)",
            "",
          );
          if (fb === null) return;
          void onRegenerate(slide.slide_id, fb);
        }}
      >
        ↻
      </button>
      <button
        type="button"
        className="thumb__delete"
        aria-label={`Delete slide ${index + 1}`}
        onClick={(e) => {
          e.stopPropagation();
          if (
            !window.confirm("Delete this slide? This cannot be undone.")
          )
            return;
          onDelete(slide.slide_id);
        }}
      >
        ×
      </button>
    </div>
  );
});

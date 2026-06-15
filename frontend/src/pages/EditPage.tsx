import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { DeckCanvas } from "../components/DeckCanvas";
import { ExportMenu } from "../components/ExportMenu";
import { InspectorPopover } from "../components/InspectorPopover";
import { PendingCommentsPanel } from "../components/PendingCommentsPanel";
import { SlideThumbnailRail, type SlideRef } from "../components/SlideThumbnailRail";
import type { Deck, PendingComment, SelectedElement } from "../types";

type PopoverState = {
  target_id: string;
  rect: { x: number; y: number; w: number; h: number };
};

export function EditPage() {
  const { deckId } = useParams<{ deckId: string }>();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [comments, setComments] = useState<PendingComment[]>([]);
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const [activeSlideId, setActiveSlideId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scale, setScale] = useState(0.5);

  const reloadData = useCallback(async () => {
    if (!deckId) return;
    const [d, c] = await Promise.all([api.getDeck(deckId), api.listDeckComments(deckId)]);
    setDeck(d);
    setComments(c);
  }, [deckId]);

  useEffect(() => {
    if (!deckId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void (async () => {
      try {
        await reloadData();
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : "Failed to load deck");
          setDeck(null);
          setComments([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deckId, reloadData]);

  // Auto-fit deck to canvas wrapper.
  useLayoutEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const computeScale = () => {
      const w = el.clientWidth - 48;
      const h = el.clientHeight - 48;
      const s = Math.min(w / 1920, h / 1080);
      setScale(Math.max(0.15, Math.min(1, s)));
    };
    computeScale();
    const ro = new ResizeObserver(computeScale);
    ro.observe(el);
    return () => ro.disconnect();
  }, [loading]);

  const { slides, deckStyles } = useMemo(() => {
    if (!deck?.html_doc) return { slides: [] as SlideRef[], deckStyles: "" };
    const doc = new DOMParser().parseFromString(deck.html_doc, "text/html");
    const styles = Array.from(doc.querySelectorAll("style"))
      .map((s) => s.textContent ?? "")
      .join("\n");
    const sectionEls = Array.from(doc.querySelectorAll<HTMLElement>("section.slide[data-slide-id]"));
    const slidesOut: SlideRef[] = sectionEls.map((s) => ({
      slide_id: s.dataset.slideId || "",
      outerHTML: s.outerHTML,
      title:
        s.querySelector("h1, h2")?.textContent?.trim() ||
        s.querySelector(".slide-eyebrow, [data-osd-id$='-eyebrow']")?.textContent?.trim() ||
        "",
    }));
    return { slides: slidesOut, deckStyles: styles };
  }, [deck?.html_doc]);

  // Validate activeSlideId against the current slides — after a regen /
  // delete / add the previously-active slide_id may no longer exist; fall
  // through to slides[0] so the preview never points at a ghost slide.
  const slideIds = useMemo(() => new Set(slides.map((s) => s.slide_id)), [slides]);
  const effectiveSlideId =
    activeSlideId && slideIds.has(activeSlideId)
      ? activeSlideId
      : slides[0]?.slide_id ?? null;

  const bumpIframe = useCallback(() => {
    setPopover(null);
    setReloadKey((k) => k + 1);
  }, []);

  const handleDeckSelect = useCallback(
    (sel: SelectedElement) => setPopover({ target_id: sel.target_id, rect: sel.rect }),
    [],
  );

  const popoverPos = useMemo(() => {
    if (!popover) return { x: 0, y: 0 };
    const stageW = 1920 * scale;
    const stageH = 1080 * scale;
    const POP_W = 320;
    const POP_H = 200;
    const right = (popover.rect.x + popover.rect.w) * scale + 12;
    const left = popover.rect.x * scale - POP_W - 12;
    const x = right + POP_W <= stageW ? right : Math.max(8, left);
    const y = Math.max(8, Math.min(popover.rect.y * scale, stageH - POP_H - 8));
    return { x, y };
  }, [popover, scale]);

  const handleDeleteSlide = useCallback(
    async (sid: string) => {
      if (!deck) return;
      setBusy(true);
      try {
        await api.deleteDeckSlide(deck.id, sid);
        await reloadData();
        bumpIframe();
        if (activeSlideId === sid) setActiveSlideId(null);
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Failed to delete slide");
      } finally {
        setBusy(false);
      }
    },
    [deck, reloadData, activeSlideId, bumpIframe],
  );

  const handleRegenerateSlide = useCallback(
    async (sid: string, feedback?: string) => {
      if (!deck) return;
      setBusy(true);
      try {
        await api.regenerateDeckSlide(deck.id, sid, feedback);
        await reloadData();
        bumpIframe();
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Failed to regenerate slide");
      } finally {
        setBusy(false);
      }
    },
    [deck, reloadData, bumpIframe],
  );

  const handleAddSlide = useCallback(
    async (prompt: string) => {
      if (!deck) return;
      setBusy(true);
      try {
        await api.addDeckSlide(deck.id, { prompt });
        await reloadData();
        bumpIframe();
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Failed to add slide");
      } finally {
        setBusy(false);
      }
    },
    [deck, reloadData, bumpIframe],
  );

  if (!deckId) {
    return (
      <div className="app edit-page">
        <main className="app-main">
          <div className="empty-state empty-state--rich">
            <div className="empty-state__mark" aria-hidden />
            <p className="empty-state__lede">Missing deck ID.</p>
            <button type="button" className="btn btn--primary" onClick={() => navigate("/")}>
              <span aria-hidden>← </span>Home
            </button>
          </div>
        </main>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="app edit-page">
        <main className="app-main">
          <div className="editor-skel" aria-busy="true" aria-label="Loading deck">
            <div className="editor-skel__bar gen-skel-line" />
            <div className="editor-skel__panels">
              <div className="editor-skel__rail gen-skel-line" />
              <div className="editor-skel__canvas gen-skel-line" />
              <div className="editor-skel__side gen-skel-line" />
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (!deck) {
    const shortId = deckId ? deckId.slice(0, 8) : null;
    return (
      <div className="app edit-page">
        <main className="app-main">
          <div className="empty-state empty-state--rich">
            <div className="empty-state__mark" aria-hidden />
            <p className="empty-state__lede">{loadError ?? "We couldn't find this deck."}</p>
            {shortId && (
              <p className="empty-state__detail mono">Deck ID: {shortId}</p>
            )}
            <div className="empty-state__actions">
              <button type="button" className="btn btn--primary" onClick={() => navigate("/")}>
                Browse your templates
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => navigate("/admin/template")}>
                Register a new template
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="editor edit-page">
      <header className="editor-header">
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate("/")}>
          <span aria-hidden>← </span>Home
        </button>
        <div
          className="editor-header__title"
          style={{
            flexDirection: "column",
            alignItems: "flex-start",
            gap: "var(--space-1)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "var(--space-3)",
              minWidth: 0,
              flexWrap: "wrap",
            }}
          >
            <span className="eyebrow editor-header__eyebrow">Deck</span>
            <strong>
              {slides.length} {slides.length === 1 ? "slide" : "slides"}
            </strong>
            <span className="editor-header__id">{deck.id.slice(0, 8)}</span>
          </div>
          {deck.created_at && (
            <p className="text-xs muted" style={{ margin: 0, fontSize: "var(--fs-micro)" }}>
              Data as of: {new Date(deck.created_at).toLocaleString()}
            </p>
          )}
        </div>
        {busy && (
          <span className="editor-header__busy" role="status" aria-live="polite">
            <span className="spinner editor-header__spinner" aria-hidden />
            Processing
          </span>
        )}
        <ExportMenu deckId={deck.id} />
      </header>
      {loadError && deck && (
        <div className="error-banner error-banner--inline error-banner--transient" role="alert">
          <span>{loadError}</span>
          <button
            type="button"
            className="btn btn--sm btn--ghost"
            onClick={() => setLoadError(null)}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}
      <div className="editor-body">
        <SlideThumbnailRail
          slides={slides}
          deckStyles={deckStyles}
          activeSlideId={effectiveSlideId}
          onSelect={setActiveSlideId}
          onAdd={handleAddSlide}
          onDelete={handleDeleteSlide}
          onRegenerate={handleRegenerateSlide}
        />
        <main className="canvas-wrap" ref={canvasRef}>
          <div
            className="canvas-stage"
            style={{ width: 1920 * scale, height: 1080 * scale }}
          >
            <div
              className="canvas-frame"
              style={{
                transform: `scale(${scale})`,
                transformOrigin: "top left",
              }}
            >
              <DeckCanvas
                deckId={deck.id}
                reloadKey={reloadKey}
                onSelect={handleDeckSelect}
                gotoSlideId={effectiveSlideId}
              />
            </div>
            {popover ? (
              <InspectorPopover
                pos={popoverPos}
                onSave={async (note) => {
                  const trimmed = note.trim();
                  if (!trimmed) return;
                  setBusy(true);
                  try {
                    await api.saveDeckComment(deck.id, {
                      target_id: popover.target_id,
                      note: trimmed,
                    });
                    const pending = await api.listDeckComments(deck.id);
                    const newComment = pending.find(
                      (c) => c.target_id === popover.target_id && c.note === trimmed,
                    );
                    if (newComment) {
                      try {
                        await api.applyDeckComment(deck.id, newComment.id);
                      } catch (e) {
                        setLoadError(
                          e instanceof Error ? e.message : "Apply failed; comment kept as pending",
                        );
                        await reloadData();
                        bumpIframe();
                        setPopover(null);
                        return;
                      }
                    }
                    await reloadData();
                    bumpIframe();
                    setPopover(null);
                  } catch (e) {
                    setLoadError(e instanceof Error ? e.message : "Failed to save comment");
                    setPopover(null);
                  } finally {
                    setBusy(false);
                  }
                }}
              onCancel={() => setPopover(null)}
            />
          ) : null}
          </div>
        </main>
        <PendingCommentsPanel
          comments={comments}
          busy={busy}
          onApply={async (cid) => {
            setBusy(true);
            try {
              await api.applyDeckComment(deck.id, cid);
              await reloadData();
              bumpIframe();
            } catch (e) {
              setLoadError(e instanceof Error ? e.message : "Failed to apply comment");
            } finally {
              setBusy(false);
            }
          }}
          onDiscard={async (cid) => {
            setBusy(true);
            try {
              await api.discardDeckComment(deck.id, cid);
              await reloadData();
            } catch (e) {
              setLoadError(e instanceof Error ? e.message : "Failed to discard comment");
            } finally {
              setBusy(false);
            }
          }}
          onApplyAll={async () => {
            setBusy(true);
            let appliedCount = 0;
            try {
              for (const c of comments) {
                try {
                  await api.applyDeckComment(deck.id, c.id);
                  appliedCount += 1;
                } catch (e) {
                  const msg = e instanceof Error ? e.message : "apply failed";
                  const unprocessed = comments.length - appliedCount;
                  const noteSnippet = c.note.length > 40 ? c.note.slice(0, 37) + "…" : c.note;
                  setLoadError(
                    `Applied ${appliedCount}/${comments.length}; stopped at "${noteSnippet}": ${msg}. ${unprocessed} unprocessed.`,
                  );
                  await reloadData();
                  bumpIframe();
                  return;
                }
              }
              await reloadData();
              bumpIframe();
            } finally {
              setBusy(false);
            }
          }}
        />
      </div>
    </div>
  );
}

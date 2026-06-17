import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { ProgressIndicator } from "../components/ProgressIndicator";
import type { GenieSpaceInfo, OutlineSlide, Template } from "../types";
import { resolveQuestions } from "./generateRequest";
import { DeckJobCancelledError, pollDeckJob } from "./pollDeckJob";

const GENERATION_STEPS = [
  "Capture widgets",
  "Compose slides",
  "Generate presentation",
  "Done",
] as const;

const OUTLINE_LAYOUTS = [
  "title",
  "section",
  "closing",
  "content",
  "one-column",
  "two-column",
  "two-column-icons",
  "three-column",
  "three-column-icons",
  "comparison",
  "pros-cons",
  "cards",
  "card-left",
  "card-right",
  "card-full",
  "big-number",
  "stat-row",
  "agenda",
  "timeline",
  "icon-grid",
  "checklist",
  "quote",
  "callout",
  "logos",
  "section-description",
] as const;

function emptySlide(): OutlineSlide {
  return { layout: "content", title: "", summary: "", notes: "" };
}

type Phase = "settings" | "outlining" | "outline-review" | "generating";

export default function GeneratePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const templateId = searchParams.get("template");
  const spaceId = searchParams.get("space");

  const [phase, setPhase] = useState<Phase>("settings");
  const [progressStep, setProgressStep] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [userPrompt, setUserPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [template, setTemplate] = useState<Template | null>(null);
  const [outlineSlides, setOutlineSlides] = useState<OutlineSlide[]>([]);
  const [highQuality, setHighQuality] = useState(false);
  const [referenceDoc, setReferenceDoc] = useState<string | null>(null);
  const [referenceDocName, setReferenceDocName] = useState<string | null>(null);
  const [refDocError, setRefDocError] = useState<string | null>(null);
  const [refDocUploading, setRefDocUploading] = useState(false);
  const [suggested, setSuggested] = useState<string[]>([]);
  const [suggestedLoading, setSuggestedLoading] = useState(false);
  const [suggestedError, setSuggestedError] = useState<string | null>(null);
  const [selectedSuggested, setSelectedSuggested] = useState<Set<string>>(() => new Set());
  const [addedQuestions, setAddedQuestions] = useState<string[]>([]);
  const [customQuestion, setCustomQuestion] = useState("");
  const [space, setSpace] = useState<GenieSpaceInfo | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!spaceId) {
      setSpace(null);
      return;
    }
    let cancelled = false;
    void api
      .getGenieSpace(spaceId)
      .then((s) => {
        if (!cancelled) setSpace(s);
      })
      .catch(() => {
        if (!cancelled) setSpace(null);
      });
    return () => {
      cancelled = true;
    };
  }, [spaceId]);

  useEffect(() => {
    if (!spaceId) {
      setSuggested([]);
      setSelectedSuggested(new Set());
      setSuggestedError(null);
      setSuggestedLoading(false);
      return;
    }
    let cancelled = false;
    setSuggestedLoading(true);
    setSuggestedError(null);
    void api
      .suggestedQuestions(spaceId)
      .then((questions) => {
        if (cancelled) return;
        setSuggested(questions);
        setSelectedSuggested(new Set(questions));
      })
      .catch((e) => {
        if (cancelled) return;
        setSuggested([]);
        setSelectedSuggested(new Set());
        setSuggestedError(e instanceof Error ? e.message : "Failed to load suggested questions");
      })
      .finally(() => {
        if (!cancelled) setSuggestedLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [spaceId]);

  useEffect(() => {
    if (!templateId) return;
    let cancelled = false;
    void api
      .getTemplate(templateId)
      .then((t) => {
        if (!cancelled) setTemplate(t);
      })
      .catch(() => {
        if (!cancelled) setTemplate(null);
      });
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  const selectedSuggestedList = useMemo(
    () => suggested.filter((q) => selectedSuggested.has(q)),
    [suggested, selectedSuggested],
  );

  const resolvedQuestions = useMemo(
    () => resolveQuestions(selectedSuggestedList, addedQuestions),
    [selectedSuggestedList, addedQuestions],
  );

  const runOutlineRequest = useCallback(
    async (failPhase: Phase) => {
      if (!templateId || !spaceId) return;
      const questions = resolveQuestions(
        suggested.filter((q) => selectedSuggested.has(q)),
        addedQuestions,
      );
      if (questions.length === 0) return;
      const prompt = userPrompt.trim();
      setError(null);
      setPhase("outlining");
      try {
        const body: Parameters<typeof api.startOutlineJob>[0] = {
          template_id: templateId,
          genie_space_id: spaceId,
          questions,
          user_prompt: prompt || undefined,
        };
        if (referenceDoc != null && referenceDocName != null) {
          body.reference_doc = referenceDoc;
          body.reference_doc_name = referenceDocName;
        }
        const { job_id } = await api.startOutlineJob(body);
        const job = await pollDeckJob(api.getOutlineJob, job_id, {
          shouldStop: () => !mountedRef.current,
        });
        if (!mountedRef.current) return;
        if (!job.slides?.length) throw new Error("Outline generation returned no slides");
        setOutlineSlides(job.slides.map((s) => ({ ...s, notes: s.notes ?? "" })));
        setPhase("outline-review");
      } catch (e) {
        if (e instanceof DeckJobCancelledError) return;
        setError(e instanceof Error ? e.message : "Outline generation failed");
        setPhase(failPhase);
      }
    },
    [templateId, spaceId, userPrompt, referenceDoc, referenceDocName, suggested, selectedSuggested, addedQuestions],
  );

  const runGenerateOutline = useCallback(async () => {
    await runOutlineRequest("settings");
  }, [runOutlineRequest]);

  const runRegenerateOutline = useCallback(async () => {
    await runOutlineRequest("outline-review");
  }, [runOutlineRequest]);

  const runBuildDeck = useCallback(async () => {
    if (!templateId || !spaceId) return;
    const questions = resolveQuestions(
      suggested.filter((q) => selectedSuggested.has(q)),
      addedQuestions,
    );
    if (questions.length === 0) return;
    const prompt = userPrompt.trim();
    setError(null);
    setPhase("generating");
    setProgressStep(0);
    try {
      const { job_id } = await api.createDeckJob({
        template_id: templateId,
        genie_space_id: spaceId,
        questions,
        user_prompt: prompt || undefined,
        outline: outlineSlides,
        high_quality: highQuality,
      });
      const job = await pollDeckJob(api.getDeckJob, job_id, {
        shouldStop: () => !mountedRef.current,
      });
      if (!mountedRef.current) return;
      setProgressStep(GENERATION_STEPS.length - 1);
      try {
        localStorage.removeItem(`genieSlide:outlineDraft:${templateId}:${spaceId}`);
      } catch {
        /* ignore */
      }
      navigate(`/decks/${job.deck_id}/edit`);
    } catch (e) {
      if (e instanceof DeckJobCancelledError) return;
      setError(e instanceof Error ? e.message : "Generation failed");
      setPhase("outline-review");
    }
  }, [
    templateId,
    spaceId,
    userPrompt,
    outlineSlides,
    highQuality,
    navigate,
    suggested,
    selectedSuggested,
    addedQuestions,
  ]);

  useEffect(() => {
    if (phase !== "outline-review") return;
    if (!templateId || !spaceId) return;
    if (outlineSlides.length === 0) return;
    const key = `genieSlide:outlineDraft:${templateId}:${spaceId}`;
    try {
      localStorage.setItem(key, JSON.stringify(outlineSlides));
    } catch {
      /* quota exceeded — silent */
    }
  }, [outlineSlides, phase, templateId, spaceId]);

  useEffect(() => {
    if (phase !== "generating") {
      setProgressStep(0);
      return;
    }
    const start = Date.now();
    const id = window.setInterval(() => {
      const elapsedSecInner = Math.floor((Date.now() - start) / 1000);
      // Heuristic: 0-10s = step 0 (CAPTURE), 10-30s = step 1 (COMPOSE),
      // 30s+ = step 2 (GENERATE). Step 3 (DONE) only when the response
      // arrives and phase transitions out of "generating".
      let step = 0;
      if (elapsedSecInner >= 30) step = 2;
      else if (elapsedSecInner >= 10) step = 1;
      setProgressStep(step);
    }, 500);
    return () => window.clearInterval(id);
  }, [phase]);

  useEffect(() => {
    if (phase !== "generating") {
      setElapsedSec(0);
      return;
    }
    const start = Date.now();
    const id = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - start) / 1000));
    }, 250);
    return () => window.clearInterval(id);
  }, [phase]);

  const goBack = useCallback(() => navigate(-1), [navigate]);
  const missingParams = !templateId || !spaceId;
  const hasQuestions = resolvedQuestions.length >= 1;
  const canGenerate = !missingParams && hasQuestions;

  const toggleSuggested = (question: string) => {
    setSelectedSuggested((prev) => {
      const next = new Set(prev);
      if (next.has(question)) next.delete(question);
      else next.add(question);
      return next;
    });
  };

  const addCustomQuestion = () => {
    const trimmed = customQuestion.trim();
    if (!trimmed) return;
    setAddedQuestions((prev) => [...prev, trimmed]);
    setCustomQuestion("");
  };

  const removeAddedQuestion = (index: number) => {
    setAddedQuestions((prev) => prev.filter((_, i) => i !== index));
  };

  const moveSlide = (index: number, dir: -1 | 1) => {
    const j = index + dir;
    if (j < 0 || j >= outlineSlides.length) return;
    setOutlineSlides((prev) => {
      const next = [...prev];
      const a = next[index];
      const b = next[j];
      if (!a || !b) return prev;
      next[index] = b;
      next[j] = a;
      return next;
    });
  };

  const updateSlide = (index: number, patch: Partial<OutlineSlide>) => {
    setOutlineSlides((prev) =>
      prev.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    );
  };

  const deleteSlide = (index: number) => {
    setOutlineSlides((prev) => prev.filter((_, i) => i !== index));
  };

  const addSlide = () => {
    setOutlineSlides((prev) => [...prev, emptySlide()]);
  };

  const handleRefDocPick = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setRefDocError(null);
    setRefDocUploading(true);
    try {
      const r = await api.uploadOutlineReferenceDoc(file);
      setReferenceDoc(r.reference_doc);
      setReferenceDocName(r.reference_doc_name);
    } catch (err) {
      setReferenceDoc(null);
      setReferenceDocName(null);
      setRefDocError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setRefDocUploading(false);
    }
  }, []);

  const clearRefDoc = useCallback(() => {
    setReferenceDoc(null);
    setReferenceDocName(null);
    setRefDocError(null);
  }, []);

  return (
    <div className="app generate-page">
      <header className="app-header">
        <div>
          <span className="eyebrow">Step 3 of 3 · Compose</span>
          <h1>Generate presentation</h1>
          {!missingParams && (
            <div className="hero-context">
              {template && (
                <span className="context-chip">
                  Template <span className="context-chip__value">{template.name}</span>
                  <button
                    type="button"
                    className="context-chip__action"
                    onClick={() => navigate("/")}
                  >
                    Change
                  </button>
                </span>
              )}
              {spaceId && (
                <span className="context-chip">
                  Genie space <span className="context-chip__value">{space?.title ?? spaceId}</span>
                  <button
                    type="button"
                    className="context-chip__action"
                    onClick={() =>
                      navigate(`/space-select?template=${encodeURIComponent(templateId ?? "")}`)
                    }
                  >
                    Change
                  </button>
                </span>
              )}
            </div>
          )}
        </div>
        <button type="button" className="btn btn--ghost" onClick={goBack}>
          <span aria-hidden>← </span>Back
        </button>
      </header>

      <main className="app-main generate-page__main">
        {missingParams && (
          <div className="empty-state">
            <p className="empty-state__lede">
              Missing template or Genie space. Choose a template and space first.
            </p>
            <button type="button" className="btn btn--primary" onClick={() => navigate("/")}>
              Go home
            </button>
          </div>
        )}

        {!missingParams && phase === "settings" && (
          <>
            {error && (
              <div className="error-banner error-banner--inline" role="alert">
                <span>{error}</span>
                <button type="button" className="btn btn--sm" onClick={() => void runGenerateOutline()}>
                  Try again
                </button>
              </div>
            )}

            <div className="generate-summary">
              <div className="generate-summary__card">
                <span className="eyebrow">Template</span>
                {template ? (
                  <>
                    <strong>{template.name}</strong>
                    {template.description && (
                      <span className="generate-summary__desc">{template.description}</span>
                    )}
                    <div className="generate-summary__swatches" aria-hidden>
                      {(["bg", "text", "accent", "muted"] as const).map((k) => {
                        const palette = (template.tokens?.palette ?? {}) as Record<string, string>;
                        const c =
                          palette[k] ??
                          template.brand[
                            k === "bg"
                              ? "secondary"
                              : k === "text"
                                ? "text_dark"
                                : k === "accent"
                                  ? "accent"
                                  : "primary"
                          ];
                        return (
                          <span
                            key={k}
                            className="generate-summary__swatch"
                            title={`${k}: ${c}`}
                            style={{ background: c }}
                          />
                        );
                      })}
                    </div>
                  </>
                ) : (
                  <div className="gen-stack" aria-hidden>
                    <span className="gen-skel-line" />
                    <span className="gen-skel-line" />
                    <span className="gen-skel-line gen-skel-line--short" />
                  </div>
                )}
              </div>
              <div className="generate-summary__card">
                <span className="eyebrow">Genie space</span>
                {spaceId ? (
                  <strong className="mono">{spaceId}</strong>
                ) : (
                  <div className="gen-stack" aria-hidden>
                    <span className="gen-skel-line" />
                    <span className="gen-skel-line gen-skel-line--short" />
                  </div>
                )}
              </div>
            </div>

            <fieldset className="fieldset">
              <legend>Questions</legend>
              <p className="gen-meta">
                Select Genie questions to ground the outline and deck. At least one is required.
              </p>
              {suggestedLoading && (
                <p className="muted gen-row">
                  <span className="spinner" /> Loading suggested questions…
                </p>
              )}
              {suggestedError && (
                <p className="gen-meta gen-meta--danger" role="status">
                  {suggestedError} You can still add your own questions below.
                </p>
              )}
              {!suggestedLoading && suggested.length > 0 && (
                <div className="question-chips" role="group" aria-label="Suggested questions">
                  {suggested.map((question) => {
                    const selected = selectedSuggested.has(question);
                    return (
                      <button
                        key={question}
                        type="button"
                        className={`question-chip${selected ? " question-chip--selected" : ""}`}
                        aria-pressed={selected}
                        onClick={() => toggleSuggested(question)}
                      >
                        {question}
                      </button>
                    );
                  })}
                </div>
              )}
              {!suggestedLoading && suggested.length === 0 && !suggestedError && spaceId && (
                <p className="dim">No suggested questions for this space. Add your own below.</p>
              )}
              {addedQuestions.length > 0 && (
                <ul className="added-questions">
                  {addedQuestions.map((question, index) => (
                    <li key={`${index}-${question}`} className="added-question">
                      <span>{question}</span>
                      <button
                        type="button"
                        className="btn btn--sm btn--ghost"
                        aria-label={`Remove question: ${question}`}
                        onClick={() => removeAddedQuestion(index)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="gen-row gen-row--wrap question-add-row">
                <label className="field">
                  <span className="field-label">Add a question</span>
                  <input
                    type="text"
                    className="input"
                    name="customQuestion"
                    autoComplete="off"
                    value={customQuestion}
                    onChange={(e) => setCustomQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addCustomQuestion();
                      }
                    }}
                    placeholder="e.g., What drove revenue growth last quarter?"
                  />
                </label>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={addCustomQuestion}
                  disabled={!customQuestion.trim()}
                >
                  Add
                </button>
              </div>
              {!hasQuestions && (
                <p className="gen-meta gen-meta--danger" role="status">
                  Select or add at least one question.
                </p>
              )}
            </fieldset>

            <fieldset className="fieldset">
              <legend>Prompt</legend>
              <label className="field">
                <span className="field-label">Reference document (optional .md/.txt)</span>
                <input
                  className="input"
                  type="file"
                  name="referenceDoc"
                  accept=".txt,.md,.markdown,text/plain,text/markdown"
                  disabled={refDocUploading}
                  onChange={(e) => void handleRefDocPick(e)}
                />
              </label>
              {refDocError && (
                <p className="gen-meta gen-meta--danger" role="alert">
                  {refDocError}
                </p>
              )}
              {referenceDocName && referenceDoc != null && (
                <div className="gen-row gen-row--wrap gen-meta--upload">
                  <span>Uploaded: {referenceDocName}</span>
                  <button type="button" className="btn btn--sm btn--ghost" onClick={clearRefDoc}>
                    Remove
                  </button>
                </div>
              )}
              <p className="gen-meta">
                The outline will be shaped around this document; Genie space data is used for evidence.
              </p>
              <label className="field">
                <span className="field-label">Instructions (optional)</span>
                <textarea
                  className="textarea"
                  name="userPrompt"
                  value={userPrompt}
                  onChange={(e) => setUserPrompt(e.target.value)}
                  placeholder="e.g., Keep it concise for executives. Highlight only the key KPIs."
                  rows={5}
                />
              </label>
              <label className="field gen-checkbox">
                <input
                  type="checkbox"
                  name="highQuality"
                  checked={highQuality}
                  onChange={(e) => setHighQuality(e.target.checked)}
                  className="gen-checkbox__input"
                />
                <span className="gen-checkbox__body">
                  <span className="gen-row gen-row--baseline gen-row--wrap">
                    <strong>High-quality mode</strong>
                    <span className="dim">— runs an automatic design audit after generation and regenerates flagged slides. Slower (~30s extra).</span>
                  </span>
                  <span className="dim gen-checkbox__hint">
                    Disabled by default — check to run an extra design audit pass (~30s slower).
                  </span>
                </span>
              </label>
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={() => void runGenerateOutline()}
                disabled={!canGenerate}
              >
                Generate
              </button>
            </fieldset>
          </>
        )}

        {!missingParams && phase === "outlining" && (
          <fieldset className="fieldset">
            <legend>Building outline</legend>
            <p className="muted gen-row">
              <span className="spinner" /> Drafting slide outline…
            </p>
            <p className="dim">Typically takes 30–60 seconds.</p>
          </fieldset>
        )}

        {!missingParams && phase === "outline-review" && (
          <>
            {error && (
              <div className="error-banner error-banner--inline" role="alert">
                <span>{error}</span>
                <button type="button" className="btn btn--sm" onClick={() => void runBuildDeck()}>
                  Try again
                </button>
              </div>
            )}

            <fieldset className="fieldset">
              <legend>Review outline</legend>
              <p className="muted outline-intro">
                Adjust layouts, titles, and summaries. Order follows top to bottom.
              </p>
              <div className="gen-stack">
                {outlineSlides.map((slide, index) => (
                  <div
                    key={`slide-${index}-${slide.title.slice(0, 12)}`}
                    className="generate-summary__card outline-card"
                  >
                    <div className="gen-row gen-row--spread">
                      <span className="eyebrow">
                        Slide {index + 1}
                      </span>
                      <div className="outline-controls" role="group" aria-label="Reorder or remove slide">
                        <button
                          type="button"
                          className="btn btn--sm btn--ghost"
                          aria-label="Move up"
                          disabled={index === 0}
                          onClick={() => moveSlide(index, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="btn btn--sm btn--ghost"
                          aria-label="Move down"
                          disabled={index === outlineSlides.length - 1}
                          onClick={() => moveSlide(index, 1)}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          className="btn btn--sm btn--ghost"
                          aria-label="Remove slide"
                          onClick={() => {
                            if (
                              !window.confirm(
                                "Delete this slide? This cannot be undone.",
                              )
                            )
                              return;
                            deleteSlide(index);
                          }}
                        >
                          ×
                        </button>
                      </div>
                    </div>
                    <label className="field">
                      <span className="field-label">Layout</span>
                      <select
                        className="select"
                        name="slideLayout"
                        value={slide.layout}
                        onChange={(e) => updateSlide(index, { layout: e.target.value })}
                      >
                        {OUTLINE_LAYOUTS.map((layout) => (
                          <option key={layout} value={layout}>
                            {layout}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span className="field-label">Title</span>
                      <input
                        type="text"
                        className="input"
                        name="slideTitle"
                        autoComplete="off"
                        value={slide.title}
                        onChange={(e) => updateSlide(index, { title: e.target.value })}
                        placeholder="e.g., Quarterly metrics overview…"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">Summary</span>
                      <textarea
                        className="textarea"
                        name="slideSummary"
                        rows={2}
                        value={slide.summary}
                        onChange={(e) => updateSlide(index, { summary: e.target.value })}
                        placeholder="e.g., Total revenue grew 18% YoY…"
                      />
                    </label>
                  </div>
                ))}
              </div>
              <div className="gen-actions">
                <button type="button" className="btn btn--ghost" onClick={addSlide}>
                  Add slide
                </button>
                <button type="button" className="btn btn--ghost" onClick={() => void runRegenerateOutline()}>
                  Regenerate outline
                </button>
                <button
                  type="button"
                  className="btn btn--primary btn--lg btn--with-arrow"
                  onClick={() => void runBuildDeck()}
                  disabled={outlineSlides.length === 0}
                >
                  <span className="btn--with-arrow__label">Build deck</span>
                  <span className="btn--with-arrow__icon-shell" aria-hidden>
                    <span className="btn--with-arrow__icon">→</span>
                  </span>
                </button>
              </div>
            </fieldset>
          </>
        )}

        {!missingParams && phase === "generating" && (
          <fieldset className="fieldset">
            <legend>Generating</legend>
            <p
              className="muted"
              style={{ margin: "0 0 16px", display: "flex", alignItems: "center", gap: 8 }}
            >
              <span className="spinner" /> Creating your presentation… ({elapsedSec}s elapsed)
            </p>
            <p className="dim">
              Typically takes 60–120 seconds. You can leave this tab open and come back.
            </p>
            <ProgressIndicator step={progressStep} steps={[...GENERATION_STEPS]} />
          </fieldset>
        )}
      </main>
    </div>
  );
}

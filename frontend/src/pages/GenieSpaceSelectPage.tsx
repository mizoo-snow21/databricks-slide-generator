import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { GenieSpaceInfo, Template } from "../types";

const FETCH_TIMEOUT_MS = 30_000;

export default function GenieSpaceSelectPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const templateId = searchParams.get("template");

  const [filter, setFilter] = useState("");
  const [spaces, setSpaces] = useState<GenieSpaceInfo[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [template, setTemplate] = useState<Template | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

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

  useEffect(() => {
    if (!templateId) {
      setSpaces(null);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const list = await api.listGenieSpaces(controller.signal);
        if (!cancelled) setSpaces(list);
      } catch (e) {
        if (!cancelled) {
          if (e instanceof Error && e.name === "AbortError") {
            setError("Request timed out. Please try again.");
          } else {
            setError(e instanceof Error ? e.message : "Failed to load Genie spaces");
          }
          setSpaces(null);
        }
      } finally {
        window.clearTimeout(timeoutId);
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [templateId, reloadKey]);

  const goBack = useCallback(() => navigate("/"), [navigate]);

  const onSelectSpace = useCallback(
    (space: GenieSpaceInfo) => {
      if (!templateId) return;
      navigate(
        `/generate?template=${encodeURIComponent(templateId)}&space=${encodeURIComponent(space.space_id)}`,
      );
    },
    [navigate, templateId],
  );

  const needle = filter.trim().toLowerCase();
  const filteredSpaces = useMemo(
    () =>
      needle === ""
        ? (spaces ?? [])
        : (spaces ?? []).filter(
            (s) =>
              s.title.toLowerCase().includes(needle) ||
              s.description.toLowerCase().includes(needle),
          ),
    [spaces, needle],
  );

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  return (
    <div className="app dashboard-select-page">
      <header className="app-header">
        <div>
          <span className="eyebrow">Step 2 of 3 · Source data</span>
          <h1>Choose a Genie space</h1>
          {template && (
            <div className="hero-context">
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
            </div>
          )}
        </div>
        <button type="button" className="btn btn--ghost" onClick={goBack}>
          <span aria-hidden>← </span>Back
        </button>
      </header>

      <main className="app-main">
        {!templateId && (
          <div className="empty-state">
            <p style={{ margin: "0 0 12px" }}>
              No template selected. Start from the home page and pick a template first.
            </p>
            <button type="button" className="btn btn--primary" onClick={goBack}>
              Go home
            </button>
          </div>
        )}

        {templateId && (
          <>
            <label className="search-bar search-bar--polish">
              <span className="search-bar__label dim mono">Filter</span>
              <input
                type="search"
                name="spaceFilter"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Search Genie spaces by title…"
                autoComplete="off"
              />
            </label>

            {loading && (
              <>
                <p className="dim dashboard-load-hint" aria-live="polite">
                  Loading Genie spaces from your workspace…
                </p>
                <div className="dashboard-select-skel" aria-busy="true">
                  <div className="gen-skel-line gen-skel-line--short" />
                </div>
              </>
            )}
            {!loading && error && (
              <div className="error-banner" role="alert">
                <span>{error}</span>
                <button type="button" className="btn btn--sm" onClick={retry}>
                  Retry
                </button>
              </div>
            )}
            {!loading && !error && spaces && filteredSpaces.length === 0 && (
              <div className="empty-state empty-state--rich">
                <div className="empty-state__mark" aria-hidden />
                <p>
                  {spaces.length === 0
                    ? "No Genie spaces available."
                    : "No Genie spaces match your search."}
                </p>
              </div>
            )}
            {!loading && !error && filteredSpaces.length > 0 && (
              <div className="card-grid">
                {filteredSpaces.map((s) => (
                  <button
                    key={s.space_id}
                    type="button"
                    className="card"
                    onClick={() => onSelectSpace(s)}
                  >
                    <div className="card-eyebrow">Genie space</div>
                    <h3 className="card-title">{s.title}</h3>
                    {s.description.trim() && <p className="card-desc">{s.description}</p>}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

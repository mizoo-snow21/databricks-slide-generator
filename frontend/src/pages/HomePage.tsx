import type { CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type TemplatePreset } from "../api";
import { TemplateCard } from "../components/TemplateCard";
import type { Template } from "../types";

export default function HomePage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [presets, setPresets] = useState<TemplatePreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creatingPreset, setCreatingPreset] = useState<string | null>(null);

  const presetSectionRef = useRef<HTMLElement | null>(null);
  const templatesSectionRef = useRef<HTMLElement | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [list, presetList] = await Promise.all([
        api.listTemplates(),
        api.listTemplatePresets().catch(() => []),
      ]);
      setTemplates(list);
      setPresets(presetList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load templates");
      setTemplates(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      await reload();
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  useEffect(() => {
    const sections = [
      presetSectionRef.current,
      templatesSectionRef.current,
    ].filter((el): el is HTMLElement => el !== null);
    if (sections.length === 0) return;

    if (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      sections.forEach((el) => el.setAttribute("data-revealed", "true"));
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.setAttribute("data-revealed", "true");
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px 25% 0px", threshold: 0 },
    );

    for (const el of sections) {
      observer.observe(el);
    }

    return () => {
      observer.disconnect();
    };
  }, [loading, presets.length, templates?.length]);

  const onSelectTemplate = useCallback(
    (t: Template) => {
      navigate(`/space-select?template=${encodeURIComponent(t.id)}`);
    },
    [navigate],
  );

  const goAdmin = useCallback(() => navigate("/admin/template"), [navigate]);

  const usePreset = useCallback(
    async (p: TemplatePreset) => {
      setCreatingPreset(p.id);
      try {
        const t = await api.createTemplateFromPreset(p.id);
        navigate(`/space-select?template=${encodeURIComponent(t.id)}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not use preset");
      } finally {
        setCreatingPreset(null);
      }
    },
    [navigate],
  );

  const presetsSection =
    !loading && presets.length > 0 ? (
      <section
        ref={presetSectionRef}
        className="home-section home-section--presets"
        data-reveal
      >
        <h2 className="section-eyebrow">Quick start · presets</h2>
        <div className="card-grid">
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              className="card"
              onClick={() => void usePreset(p)}
              disabled={creatingPreset !== null}
            >
              <div className="card-eyebrow">
                <span
                  className="card-eyebrow__accent"
                  style={{ "--card-accent": p.tokens.palette.accent } as CSSProperties}
                  aria-hidden
                />
                Preset
              </div>
              <h3 className="card-title">{p.name}</h3>
              <p className="card-desc">{p.description}</p>
              <div className="card-meta">
                <span>{creatingPreset === p.id ? "Creating…" : "Use this preset"}</span>
                <span className="card-meta__palette" aria-hidden>
                  {[
                    p.tokens.palette.bg,
                    p.tokens.palette.text,
                    p.tokens.palette.accent,
                    p.tokens.palette.muted,
                  ].map((c, i) => (
                    <span
                      key={`${p.id}-${i}`}
                      className="card-meta__palette-chip"
                      style={{ background: c }}
                    />
                  ))}
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>
    ) : null;

  const templatesSection = (
    <section
      ref={templatesSectionRef}
      className="home-section home-section--templates"
      data-reveal
    >
      <h2 className="section-eyebrow">Your templates</h2>
      {loading && (
        <div className="home-skeleton-grid" aria-busy role="status" aria-label="Loading templates">
          <div className="home-skeleton-card" />
          <div className="home-skeleton-card" />
          <div className="home-skeleton-card" />
        </div>
      )}
      {!loading && templates && templates.length === 0 && (
        <div className="empty-state">
          {presets.length > 0 ? (
            <>
              No saved templates yet. Try a <strong>preset</strong> above or click{" "}
              <strong>+ New template</strong> to author one from scratch.
            </>
          ) : (
            <>
              No saved templates yet. Click <strong>+ New template</strong> to author one from scratch.
            </>
          )}
        </div>
      )}
      {!loading && templates && templates.length > 0 && (
        <div className="card-grid card-grid--bento">
          {templates.map((t) => (
            <TemplateCard key={t.id} template={t} onSelect={onSelectTemplate} />
          ))}
        </div>
      )}
    </section>
  );

  return (
    <div className="app home-page">
      <header className="app-header home-hero">
        <div className="home-hero__col home-hero__col--left">
          <span className="home-hero__eyebrow">
            Genie Slide · Templates
          </span>
          <h1 className="home-hero__title">Choose a template</h1>
          <p className="home-hero__descriptor">
            Pick a template — then pick a Genie space, and we&apos;ll generate slides from your data.
          </p>
        </div>
        <div className="home-hero__col home-hero__col--right">
          <button type="button" className="btn btn--ghost" onClick={goAdmin}>
            Or build your own →
          </button>
        </div>
      </header>

      <main className="app-main">
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        {templates && templates.length > 0 ? (
          <>
            {templatesSection}
            {presetsSection}
          </>
        ) : (
          <>
            {presetsSection}
            {templatesSection}
          </>
        )}
      </main>
    </div>
  );
}

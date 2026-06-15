import { useCallback, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { DesignTokens } from "../types";
import { buildCreateTemplatePayload, saveDisabledReason } from "./adminTemplatePayload";

const HEX6 = /^#[0-9A-Fa-f]{6}$/;
const pickerSafeHex = (v: string) => (HEX6.test(v) ? v : "#333333");

const DEFAULT_TOKENS: DesignTokens = {
  palette: { bg: "#0a0a0a", text: "#f6f3ec", accent: "#ff4f1a", muted: "#8a8a8a" },
  fonts: { display: "'DM Sans', sans-serif", body: "'DM Sans', sans-serif" },
  typeScale: { hero: 200, title: 88, body: 36, caption: 24 },
  spacing: { padding: 120, gap: 48 },
  radius: 0,
};

export default function AdminTemplatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [googleSlidesTemplateId, setGoogleSlidesTemplateId] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [primaryColor, setPrimaryColor] = useState("#333333");
  const [font, setFont] = useState("Noto Sans JP");
  const [slideMin, setSlideMin] = useState("6");
  const [slideMax, setSlideMax] = useState("12");
  const [structureHint, setStructureHint] = useState("");
  const [styleNotes, setStyleNotes] = useState("");
  const [tokens, setTokens] = useState<DesignTokens>(() => ({ ...DEFAULT_TOKENS }));
  const [tokensTouched, setTokensTouched] = useState(false);
  const [themeMarkdown, setThemeMarkdown] = useState("");

  const updateTokens = useCallback((next: DesignTokens) => {
    setTokensTouched(true);
    setTokens(next);
  }, []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const pptxFileRef = useRef<HTMLInputElement | null>(null);
  const [pptxExtracting, setPptxExtracting] = useState(false);
  const [pptxUploadId, setPptxUploadId] = useState<string | null>(null);
  const [pptxFileName, setPptxFileName] = useState<string | null>(null);

  const goBack = useCallback(() => navigate("/"), [navigate]);

  const onImportFromGoogleSlides = useCallback(async () => {
    setError(null);
    setImportNotice(null);
    if (!importUrl.trim()) return;
    setImporting(true);
    try {
      const result = await api.importTemplateFromGoogleSlides(importUrl.trim());
      setGoogleSlidesTemplateId(result.google_slides_template_id);
      if (!name.trim()) setName(result.suggested_name);
      setTokens(result.tokens);
      setTokensTouched(true);
      setThemeMarkdown(result.theme_markdown);
      setImportNotice(`Imported "${result.suggested_name}". Review and save.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }, [importUrl, name]);

  const onPickPptx = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      setError(null);
      setPptxExtracting(true);
      try {
        const result = await api.extractTemplateFromPptx(file);
        if (!name.trim()) setName(result.suggested_name);
        setTokens(result.tokens);
        setTokensTouched(true);
        if (result.theme_markdown) setThemeMarkdown(result.theme_markdown);
        setPptxUploadId(result.upload_id);
        setPptxFileName(file.name);
      } catch (err) {
        setError(err instanceof Error ? err.message : "PPTX extract failed");
      } finally {
        setPptxExtracting(false);
      }
    },
    [name],
  );

  const onSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setError(null);

      const trimmedName = name.trim();
      const trimmedId = googleSlidesTemplateId.trim();
      if (!trimmedName) {
        setError("Name is required.");
        return;
      }
      if (!trimmedId && !pptxUploadId) {
        setError("Google Slides Template ID is required unless you upload a PPTX above.");
        return;
      }
      const color = primaryColor.trim();
      if (!HEX6.test(color)) {
        setError("Primary brand color must be a hex value like #RRGGBB.");
        return;
      }
      const min = Number(slideMin);
      const max = Number(slideMax);
      if (!Number.isInteger(min) || !Number.isInteger(max) || min < 1 || max < 1) {
        setError("Slide count min and max must be positive integers.");
        return;
      }
      if (min > max) {
        setError("Slide count minimum cannot be greater than maximum.");
        return;
      }

      const payload = buildCreateTemplatePayload({
        name: trimmedName,
        description,
        googleSlidesTemplateId: trimmedId,
        theme,
        primaryColor: color,
        font,
        slideMin: min,
        slideMax: max,
        structureHint,
        styleNotes,
        tokens,
        tokensTouched,
        themeMarkdown,
        pptxUploadId,
      });

      setSaving(true);
      try {
        await api.createTemplate(payload);
        navigate("/");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save template.");
      } finally {
        setSaving(false);
      }
    },
    [
      name,
      description,
      googleSlidesTemplateId,
      theme,
      primaryColor,
      font,
      slideMin,
      slideMax,
      structureHint,
      styleNotes,
      tokens,
      tokensTouched,
      themeMarkdown,
      navigate,
      pptxUploadId,
    ],
  );

  const saveBlockedReason = saveDisabledReason({
    name,
    googleSlidesTemplateId,
    hasPptx: pptxUploadId !== null,
  });
  const canSave = saveBlockedReason === null && !saving;

  return (
    <div className="app admin-template-page">
      <header className="app-header">
        <div>
          <span className="eyebrow">Admin · Template</span>
          <h1>Register template</h1>
        </div>
        <button type="button" className="btn btn--ghost" onClick={goBack}>
          <span aria-hidden>← </span>Back
        </button>
      </header>

      <main className="app-main admin-main">
        {error && <div className="error-banner" role="alert">{error}</div>}

        <p className="admin-intro admin-intro--lead">
          Pick one way to provide your brand source:
        </p>

        <fieldset className="fieldset">
          <legend>Option A — From a Google Slides URL</legend>
          <p className="muted admin-intro">
            Paste a Google Slides URL or presentation ID — we{'\u2019'}ll read the deck{'\u2019'}s
            theme and pre-fill colors, fonts, and the GSlides template ID.
            Requires gcloud auth on the server.
          </p>
          <div className="gen-row">
            <input
              className="input"
              type="url"
              inputMode="url"
              name="importUrl"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="https://docs.google.com/presentation/d/…"
              disabled={importing || saving}
              autoComplete="off"
            />
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => void onImportFromGoogleSlides()}
              disabled={importing || saving || !importUrl.trim()}
            >
              {importing ? (
                <>
                  <span className="spinner" /> Importing…
                </>
              ) : (
                "Auto-fill"
              )}
            </button>
          </div>
          {importNotice && (
            <p className="mono admin-import-notice" role="status">
              {importNotice}
            </p>
          )}
        </fieldset>

        <fieldset className="fieldset">
          <legend>Option B — From a PPTX file</legend>
          <p className="admin-intro">
            Drop a .pptx — we extract its colors and fonts to pre-fill this form, and store the file as your template&apos;s deck-export source. Review the extracted values below, then save the template.
          </p>
          <div className="gen-row">
            <input
              ref={pptxFileRef}
              className="input"
              type="file"
              accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
              onChange={onPickPptx}
              disabled={pptxExtracting || saving}
            />
            {pptxFileName && (
              <span className="admin-import-notice" role="status">
                Pre-filled from {pptxFileName}. Review and save.
              </span>
            )}
          </div>
        </fieldset>

        <form onSubmit={(e) => void onSubmit(e)} autoComplete="off">
          <p className="admin-intro">
            Option C — Fill in the details below manually if you prefer not to use A or B.
          </p>
          <fieldset className="fieldset">
            <legend>Identity</legend>
            <label className="field">
              <span className="field-label">
                Name<span className="field-required">*</span>
              </span>
              <input
                className="input"
                type="text"
                name="templateName"
                autoComplete="off"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={saving}
              />
            </label>
            <label className="field">
              <span className="field-label">Description</span>
              <input
                className="input"
                type="text"
                name="description"
                autoComplete="off"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={saving}
              />
            </label>
            <label className="field">
              <span className="field-label">
                Google Slides Template ID
                {!pptxUploadId && <span className="field-required">*</span>}
                {pptxUploadId && <span className="field-optional"> (optional with PPTX)</span>}
              </span>
              <input
                className="input"
                type="text"
                name="googleSlidesTemplateId"
                autoComplete="off"
                spellCheck={false}
                value={googleSlidesTemplateId}
                onChange={(e) => setGoogleSlidesTemplateId(e.target.value)}
                placeholder="ID from the template URL"
                disabled={saving}
              />
            </label>
            <label className="field">
              <span className="field-label">Theme</span>
              <select
                className="select"
                name="theme"
                value={theme}
                onChange={(e) => setTheme(e.target.value as "light" | "dark")}
                disabled={saving}
              >
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
          </fieldset>

          <fieldset className="fieldset">
            <legend>Brand</legend>
            <label className="field">
              <span className="field-label">Primary brand color</span>
              <div className="gen-row">
                <input
                  type="color"
                  name="primaryColorPicker"
                  className="admin-color-picker"
                  aria-label="Primary brand color picker"
                  value={pickerSafeHex(primaryColor)}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  disabled={saving}
                />
                <input
                  className="input"
                  type="text"
                  name="primaryColor"
                  autoComplete="off"
                  spellCheck={false}
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  placeholder="#333333"
                  disabled={saving}
                />
              </div>
            </label>
            <label className="field">
              <span className="field-label">Font</span>
              <input
                className="input"
                type="text"
                name="font"
                autoComplete="off"
                spellCheck={false}
                value={font}
                onChange={(e) => setFont(e.target.value)}
                disabled={saving}
              />
            </label>
          </fieldset>

          <fieldset className="fieldset">
            <legend>Slide guidelines</legend>
            <div className="field-row">
              <label className="field">
                <span className="field-label">Min slides</span>
                <input
                  className="input"
                  type="number"
                  name="slideMin"
                  min={1}
                  autoComplete="off"
                  inputMode="numeric"
                  value={slideMin}
                  onChange={(e) => setSlideMin(e.target.value)}
                  disabled={saving}
                />
              </label>
              <label className="field">
                <span className="field-label">Max slides</span>
                <input
                  className="input"
                  type="number"
                  name="slideMax"
                  min={1}
                  autoComplete="off"
                  inputMode="numeric"
                  value={slideMax}
                  onChange={(e) => setSlideMax(e.target.value)}
                  disabled={saving}
                />
              </label>
            </div>
            <label className="field">
              <span className="field-label">Structure hint</span>
              <input
                className="input"
                type="text"
                name="structureHint"
                value={structureHint}
                onChange={(e) => setStructureHint(e.target.value)}
                disabled={saving}
              />
            </label>
            <label className="field">
              <span className="field-label">Style notes</span>
              <textarea
                className="textarea"
                name="styleNotes"
                value={styleNotes}
                onChange={(e) => setStyleNotes(e.target.value)}
                disabled={saving}
              />
            </label>
          </fieldset>

          <details className="admin-advanced">
            <summary className="admin-advanced__summary">
              Advanced design tokens (optional — defaults work for most templates)
            </summary>
            <fieldset className="fieldset">
              <legend>Design tokens · palette</legend>
              <div className="field-row">
                {(["bg", "text", "accent", "muted"] as const).map((k) => (
                  <label key={k} className="field">
                    <span className="field-label">{k.toUpperCase()}</span>
                    <input
                      className="input"
                      type="text"
                      name={`palette-${k}`}
                      spellCheck={false}
                      value={tokens.palette[k] ?? ""}
                      onChange={(e) =>
                        updateTokens({
                          ...tokens,
                          palette: { ...tokens.palette, [k]: e.target.value },
                        })
                      }
                      disabled={saving}
                    />
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset className="fieldset">
              <legend>Design tokens · fonts</legend>
              <label className="field">
                <span className="field-label">Display</span>
                <input
                  className="input"
                  type="text"
                  name="fonts-display"
                  spellCheck={false}
                  value={tokens.fonts.display}
                  onChange={(e) =>
                    updateTokens({
                      ...tokens,
                      fonts: { ...tokens.fonts, display: e.target.value },
                    })
                  }
                  disabled={saving}
                />
              </label>
              <label className="field">
                <span className="field-label">Body</span>
                <input
                  className="input"
                  type="text"
                  name="fonts-body"
                  spellCheck={false}
                  value={tokens.fonts.body}
                  onChange={(e) =>
                    updateTokens({
                      ...tokens,
                      fonts: { ...tokens.fonts, body: e.target.value },
                    })
                  }
                  disabled={saving}
                />
              </label>
            </fieldset>

            <fieldset className="fieldset">
              <legend>Type scale (px)</legend>
              <div className="field-row">
                {(["hero", "title", "body", "caption"] as const).map((k) => (
                  <label key={k} className="field">
                    <span className="field-label">{k.toUpperCase()}</span>
                    <input
                      className="input"
                      type="number"
                      name={`typeScale-${k}`}
                      min={1}
                      value={tokens.typeScale[k]}
                      onChange={(e) =>
                        updateTokens({
                          ...tokens,
                          typeScale: { ...tokens.typeScale, [k]: Number(e.target.value) },
                        })
                      }
                      disabled={saving}
                    />
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset className="fieldset">
              <legend>Spacing & radius</legend>
              <div className="field-row">
                <label className="field">
                  <span className="field-label">Padding (px)</span>
                  <input
                    className="input"
                    type="number"
                    name="paddingPx"
                    min={0}
                    value={tokens.spacing.padding}
                    onChange={(e) =>
                      updateTokens({
                        ...tokens,
                        spacing: { ...tokens.spacing, padding: Number(e.target.value) },
                      })
                    }
                    disabled={saving}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Gap (px)</span>
                  <input
                    className="input"
                    type="number"
                    name="gapPx"
                    min={0}
                    value={tokens.spacing.gap}
                    onChange={(e) =>
                      updateTokens({
                        ...tokens,
                        spacing: { ...tokens.spacing, gap: Number(e.target.value) },
                      })
                    }
                    disabled={saving}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Radius (px)</span>
                  <input
                    className="input"
                    type="number"
                    name="radiusPx"
                    min={0}
                    value={tokens.radius}
                    onChange={(e) =>
                      updateTokens({ ...tokens, radius: Number(e.target.value) })
                    }
                    disabled={saving}
                  />
                </label>
              </div>
            </fieldset>

            <fieldset className="fieldset">
              <legend>Theme narrative</legend>
              <label className="field">
                <span className="field-label">Narrative (markdown)</span>
                <textarea
                  className="textarea"
                  name="themeMarkdown"
                  value={themeMarkdown}
                  onChange={(e) => setThemeMarkdown(e.target.value)}
                  placeholder="Editorial monochrome with one hot accent…"
                  rows={6}
                  disabled={saving}
                />
              </label>
            </fieldset>
          </details>

          {saveBlockedReason && (
            <p className="muted admin-intro" role="status">
              {saveBlockedReason}
            </p>
          )}
          <button type="submit" className="btn btn--primary btn--lg" disabled={!canSave}>
            {saving ? (
              <>
                <span className="spinner" /> Saving…
              </>
            ) : (
              "Save template"
            )}
          </button>
        </form>
      </main>
    </div>
  );
}

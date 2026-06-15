import type { DesignTokens } from "../types";
import { buildCreateTemplatePayload } from "./adminTemplatePayload";

/** Same behavior as `assert.equal` from `node:assert` (no @types/node in project). */
function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  }
}

const SAMPLE_TOKENS: DesignTokens = {
  palette: { bg: "#111111", text: "#eeeeee", accent: "#ff0000", muted: "#888888" },
  fonts: { display: "Display Font", body: "Body Font" },
  typeScale: { hero: 100, title: 50, body: 24, caption: 12 },
  spacing: { padding: 80, gap: 32 },
  radius: 4,
};

const baseForm = {
  name: "My Template",
  description: "A demo template",
  googleSlidesTemplateId: "abc123",
  theme: "dark" as const,
  primaryColor: "#123456",
  font: "Inter",
  slideMin: 6,
  slideMax: 12,
  structureHint: "intro then content",
  styleNotes: "keep it minimal",
  tokens: SAMPLE_TOKENS,
  tokensTouched: false,
  themeMarkdown: "optional narrative",
  pptxUploadId: null as string | null,
};

// tokensTouched=false -> payload.tokens === undefined
{
  const payload = buildCreateTemplatePayload(baseForm);
  assertEqual(payload.tokens, undefined);
}

// tokensTouched=true -> payload.tokens === the passed tokens object
{
  const payload = buildCreateTemplatePayload({ ...baseForm, tokensTouched: true });
  assertEqual(payload.tokens, SAMPLE_TOKENS);
}

// brand.accent === primary color
{
  const payload = buildCreateTemplatePayload(baseForm);
  assertEqual(payload.brand?.accent, "#123456");
  assertEqual(payload.brand?.primary, "#123456");
}

// passthrough fields preserved
{
  const payload = buildCreateTemplatePayload(baseForm);
  assertEqual(payload.name, "My Template");
  assertEqual(payload.theme, "dark");
  assertEqual(payload.google_slides_template_id, "abc123");
  assertEqual(payload.description, "A demo template");
}

console.log("All assertions passed");

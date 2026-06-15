import type {
  DesignTokens,
  TemplateBrand,
  TemplateCreate,
  TemplateGuidelines,
} from "../types";

export const DEFAULT_BRAND_REST: Omit<TemplateBrand, "primary" | "font" | "accent"> = {
  secondary: "#666666",
  text_dark: "#202124",
  text_light: "#FFFFFF",
};

const DEFAULT_GUIDELINES_REST: Omit<
  TemplateGuidelines,
  "total_slides_min" | "total_slides_max" | "structure_hint" | "style_notes"
> = {
  preferred_layouts: ["title", "content_basic", "content_2col", "title_only", "closing"],
  must_include: ["title", "closing"],
  chart_preference: "auto",
};

export interface SaveDisabledReasonInput {
  name: string;
  googleSlidesTemplateId: string;
  hasPptx: boolean;
}

export function saveDisabledReason(input: SaveDisabledReasonInput): string | null {
  if (!input.name.trim()) {
    return "Enter a template name to save.";
  }
  if (!input.googleSlidesTemplateId.trim() && !input.hasPptx) {
    return "Add a Google Slides Template ID above, or upload a PPTX, to save.";
  }
  return null;
}

export interface AdminTemplateFormInput {
  name: string;
  description: string;
  googleSlidesTemplateId: string;
  theme: "light" | "dark";
  primaryColor: string;
  font: string;
  slideMin: number;
  slideMax: number;
  structureHint: string;
  styleNotes: string;
  tokens: DesignTokens;
  tokensTouched: boolean;
  themeMarkdown?: string;
  pptxUploadId?: string | null;
}

export function buildCreateTemplatePayload(form: AdminTemplateFormInput): TemplateCreate {
  const font = form.font.trim() || "Noto Sans JP";
  const brand: TemplateBrand = {
    ...DEFAULT_BRAND_REST,
    primary: form.primaryColor,
    accent: form.primaryColor,
    font,
  };
  const guidelines: TemplateGuidelines = {
    ...DEFAULT_GUIDELINES_REST,
    total_slides_min: form.slideMin,
    total_slides_max: form.slideMax,
    structure_hint: form.structureHint.trim(),
    style_notes: form.styleNotes.trim(),
  };
  return {
    name: form.name,
    description: form.description.trim(),
    google_slides_template_id: form.googleSlidesTemplateId,
    theme: form.theme,
    brand,
    guidelines,
    tokens: form.tokensTouched ? form.tokens : undefined,
    theme_markdown: form.themeMarkdown?.trim() || undefined,
    pptx_upload_id: form.pptxUploadId ?? undefined,
  };
}

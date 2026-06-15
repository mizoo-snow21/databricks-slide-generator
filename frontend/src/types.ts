export interface TemplateBrand {
  primary: string;
  secondary: string;
  accent: string;
  text_dark: string;
  text_light: string;
  font: string;
}

export interface TemplateGuidelines {
  total_slides_min: number;
  total_slides_max: number;
  structure_hint: string;
  preferred_layouts: string[];
  style_notes: string;
  must_include: string[];
  chart_preference: string;
}

export type DesignTokens = {
  palette: { bg: string; text: string; accent: string; muted: string; [k: string]: string };
  fonts: { display: string; body: string };
  typeScale: { hero: number; title: number; body: number; caption: number };
  spacing: { padding: number; gap: number };
  radius: number;
};

export interface PptxExtractResult {
  upload_id: string;
  suggested_name: string;
  theme_markdown: string;
  tokens: DesignTokens;
}

export interface Template {
  id: string;
  name: string;
  description: string;
  thumbnail_url: string | null;
  google_slides_template_id: string;
  theme: string;
  brand: TemplateBrand;
  guidelines: TemplateGuidelines;
  created_by: string;
  created_at: string | null;
  tokens?: Partial<DesignTokens> & Record<string, unknown>;
  theme_markdown?: string;
}

export interface TemplateCreate {
  name: string;
  description?: string;
  google_slides_template_id: string;
  theme?: string;
  brand?: TemplateBrand;
  guidelines?: TemplateGuidelines;
  tokens?: Partial<DesignTokens> & Record<string, unknown>;
  theme_markdown?: string;
  pptx_upload_id?: string;
}

export interface GenieSpaceInfo {
  space_id: string;
  title: string;
  description: string;
}

export interface OutlineSlide {
  layout: string;
  title: string;
  summary: string;
  notes: string;
}

export interface GenerationRequest {
  template_id: string;
  genie_space_id: string;
  questions: string[];
  user_prompt?: string;
  format?: "html" | "pptx" | null;
  outline?: OutlineSlide[] | null;
  high_quality?: boolean;
}

export interface Deck {
  id: string;
  user_id: string;
  template_id: string;
  genie_space_id: string;
  questions: string[];
  google_slides_template_id: string;
  user_prompt: string | null;
  html_doc: string;
  design_tokens: Partial<DesignTokens> & Record<string, unknown>;
  theme_markdown: string;
  status: "draft" | "exported";
  gslides_file_id?: string | null;
  gslides_url?: string | null;
  chart_warnings?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface AuditIssue {
  slide_id: string;
  severity: string;
  message: string;
  fix_hint: string;
}

export interface AuditResponse {
  deck: Deck;
  issues: AuditIssue[];
}

export interface PendingComment {
  id: string;
  target_id: string;
  note: string;
  ts: string;
}

export interface DeckMutationResponse {
  deck: Deck;
  revision_no: number;
}

export type SelectedElementRect = { x: number; y: number; w: number; h: number };
export type SelectedElement = { target_id: string; rect: SelectedElementRect };

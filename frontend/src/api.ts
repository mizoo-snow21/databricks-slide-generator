import type {
  AuditResponse,
  Deck,
  DeckJobStatus,
  DeckMutationResponse,
  DesignTokens,
  GenieSpaceInfo,
  OutlineJobStatus,
  OutlineSlide,
  PendingComment,
  PptxExtractResult,
  Template,
  TemplateCreate,
} from "./types";

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return response.statusText || `HTTP ${response.status}`;
  }
  try {
    const body: unknown = JSON.parse(text);
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // not JSON
  }
  return text;
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const text = await response.text();
  if (!text) {
    throw new Error("Empty response body");
  }
  try {
    return JSON.parse(text) as T;
  } catch (e) {
    const excerpt = text.length > 200 ? text.slice(0, 197) + "…" : text;
    throw new Error(`Failed to parse response JSON: ${e instanceof Error ? e.message : "unknown"}; body: ${excerpt}`);
  }
}

const jsonHeaders = {
  "Content-Type": "application/json",
} as const;

export interface TemplatePreset {
  id: string;
  name: string;
  description: string;
  tokens: DesignTokens;
  theme_markdown: string;
}

export interface GoogleSlidesImportResult {
  google_slides_template_id: string;
  suggested_name: string;
  tokens: DesignTokens;
  theme_markdown: string;
}

export const api = {
  async listTemplates(): Promise<Template[]> {
    return fetchJson<Template[]>("/api/templates");
  },

  async listTemplatePresets(): Promise<TemplatePreset[]> {
    return fetchJson<TemplatePreset[]>("/api/templates/presets");
  },

  async createTemplateFromPreset(presetId: string): Promise<Template> {
    return fetchJson<Template>(
      `/api/templates/from-preset/${encodeURIComponent(presetId)}`,
      { method: "POST", headers: jsonHeaders },
    );
  },

  async importTemplateFromGoogleSlides(
    url: string,
  ): Promise<GoogleSlidesImportResult> {
    return fetchJson<GoogleSlidesImportResult>(
      "/api/templates/import-from-google-slides",
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ url }),
      },
    );
  },

  async extractTemplateFromPptx(file: File): Promise<PptxExtractResult> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/templates/extract-pptx", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    return (await response.json()) as PptxExtractResult;
  },

  async getTemplate(id: string): Promise<Template> {
    return fetchJson<Template>(`/api/templates/${encodeURIComponent(id)}`);
  },

  async createTemplate(data: TemplateCreate): Promise<Template> {
    return fetchJson<Template>("/api/templates", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(data),
    });
  },

  async deleteTemplate(id: string): Promise<void> {
    const response = await fetch(`/api/templates/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
  },

  async listGenieSpaces(signal?: AbortSignal): Promise<GenieSpaceInfo[]> {
    return fetchJson<GenieSpaceInfo[]>("/api/genie/spaces", { signal });
  },

  async getGenieSpace(spaceId: string): Promise<GenieSpaceInfo> {
    return fetchJson<GenieSpaceInfo>(
      `/api/genie/spaces/${encodeURIComponent(spaceId)}`,
    );
  },

  async suggestedQuestions(spaceId: string): Promise<string[]> {
    const resp = await fetchJson<{ questions: string[] }>(
      `/api/genie/spaces/${encodeURIComponent(spaceId)}/suggested-questions`,
      { method: "POST", headers: jsonHeaders },
    );
    return resp.questions;
  },

  async listDecks(): Promise<Deck[]> {
    return fetchJson<Deck[]>("/api/decks");
  },

  async getDeck(id: string): Promise<Deck> {
    return fetchJson<Deck>(`/api/decks/${encodeURIComponent(id)}`);
  },

  async createDeckJob(body: {
    template_id: string;
    genie_space_id: string;
    questions: string[];
    user_prompt?: string;
    outline?: OutlineSlide[];
    high_quality?: boolean;
  }): Promise<{ job_id: string; status: string }> {
    return fetchJson<{ job_id: string; status: string }>("/api/decks", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    });
  },

  async getDeckJob(jobId: string): Promise<DeckJobStatus> {
    return fetchJson<DeckJobStatus>(`/api/decks/jobs/${encodeURIComponent(jobId)}`);
  },

  async importPptx(file: File, templateId: string): Promise<Deck> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("template_id", templateId);
    const response = await fetch("/api/decks/import-pptx", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    return (await response.json()) as Deck;
  },

  async auditDeck(deckId: string): Promise<AuditResponse> {
    return fetchJson<AuditResponse>(`/api/decks/${encodeURIComponent(deckId)}/audit`, {
      method: "POST",
      headers: jsonHeaders,
    });
  },

  async startOutlineJob(body: {
    template_id: string;
    genie_space_id: string;
    questions: string[];
    user_prompt?: string;
    reference_doc?: string;
    reference_doc_name?: string;
  }): Promise<{ job_id: string; status: string }> {
    return fetchJson<{ job_id: string; status: string }>("/api/decks/outline", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    });
  },

  async getOutlineJob(jobId: string): Promise<OutlineJobStatus> {
    return fetchJson<OutlineJobStatus>(
      `/api/decks/outline/jobs/${encodeURIComponent(jobId)}`,
    );
  },

  async uploadOutlineReferenceDoc(file: File): Promise<{
    reference_doc: string;
    reference_doc_name: string;
  }> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/decks/outline/upload-doc", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    return (await response.json()) as { reference_doc: string; reference_doc_name: string };
  },

  async exportGoogleSlides(deckId: string): Promise<{
    url: string;
    presentationId?: string;
    experimental?: boolean;
    export_note?: string;
  }> {
    return fetchJson<{
      url: string;
      presentationId?: string;
      experimental?: boolean;
      export_note?: string;
    }>(`/api/decks/${encodeURIComponent(deckId)}/export/google_slides`);
  },

  async listDeckComments(deckId: string): Promise<PendingComment[]> {
    return fetchJson<PendingComment[]>(`/api/decks/${encodeURIComponent(deckId)}/comments`);
  },

  async saveDeckComment(deckId: string, body: { target_id: string; note: string }): Promise<DeckMutationResponse> {
    return fetchJson<DeckMutationResponse>(
      `/api/decks/${encodeURIComponent(deckId)}/comments`,
      { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) },
    );
  },

  async applyDeckComment(deckId: string, commentId: string): Promise<DeckMutationResponse> {
    return fetchJson<DeckMutationResponse>(
      `/api/decks/${encodeURIComponent(deckId)}/comments/${encodeURIComponent(commentId)}/apply`,
      { method: "POST", headers: jsonHeaders },
    );
  },

  async discardDeckComment(deckId: string, commentId: string): Promise<DeckMutationResponse> {
    return fetchJson<DeckMutationResponse>(
      `/api/decks/${encodeURIComponent(deckId)}/comments/${encodeURIComponent(commentId)}`,
      { method: "DELETE" },
    );
  },

  async addDeckSlide(deckId: string, body: { prompt: string }): Promise<DeckMutationResponse> {
    return fetchJson<DeckMutationResponse>(
      `/api/decks/${encodeURIComponent(deckId)}/slides`,
      { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) },
    );
  },

  async deleteDeckSlide(deckId: string, slideId: string): Promise<DeckMutationResponse> {
    return fetchJson<DeckMutationResponse>(
      `/api/decks/${encodeURIComponent(deckId)}/slides/${encodeURIComponent(slideId)}`,
      { method: "DELETE" },
    );
  },

  async regenerateDeckSlide(deckId: string, slideId: string, feedback?: string): Promise<DeckMutationResponse> {
    return fetchJson<DeckMutationResponse>(
      `/api/decks/${encodeURIComponent(deckId)}/slides/${encodeURIComponent(slideId)}/regenerate`,
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ feedback: feedback ?? "" }),
      },
    );
  },

  deckEditUrl(deckId: string): string {
    return `/api/decks/${encodeURIComponent(deckId)}/edit-html`;
  },

  deckExportUrl(
    deckId: string,
    format: "google_slides" | "pptx" | "pdf" | "html",
  ): string {
    return `/api/decks/${encodeURIComponent(deckId)}/export/${format}`;
  },
};

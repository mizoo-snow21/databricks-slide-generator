import type { CSSProperties } from "react";

import type { Template } from "../types";

export interface TemplateCardProps {
  template: Template;
  onSelect: (template: Template) => void;
}

export function TemplateCard({ template, onSelect }: TemplateCardProps) {
  const min = template.guidelines.total_slides_min;
  const max = template.guidelines.total_slides_max;
  const slideRange = min === max ? `${min} slides` : `${min}–${max} slides`;
  const accent = template.tokens?.palette?.accent;
  const theme = template.theme?.trim();

  return (
    <button type="button" className="card" onClick={() => onSelect(template)}>
      <div className="card-eyebrow">
        {accent ? (
          <span
            className="card-eyebrow__accent"
            style={{ "--card-accent": accent } as CSSProperties}
            aria-hidden
          />
        ) : null}
        Template
      </div>
      <h3 className="card-title">{template.name}</h3>
      {template.description.trim() && (
        <p className="card-desc">{template.description}</p>
      )}
      <div className="card-meta">
        <span>{slideRange}</span>
        <span className="card-meta__trail">
          {theme ? (
            <>
              <span className="card-meta__sep" aria-hidden="true">
                ·
              </span>
              {theme}
            </>
          ) : (
            "—"
          )}
        </span>
      </div>
    </button>
  );
}

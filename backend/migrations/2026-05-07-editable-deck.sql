-- Run against your UC catalog/schema. Substitute {{catalog}} and {{schema}} with env values.

ALTER TABLE {{catalog}}.{{schema}}.templates
  ADD COLUMNS (
    tokens STRING COMMENT 'JSON: DesignTokens',
    theme_markdown STRING COMMENT 'Theme narrative (markdown)'
  );

CREATE TABLE IF NOT EXISTS {{catalog}}.{{schema}}.decks (
  id STRING NOT NULL,
  user_id STRING NOT NULL,
  template_id STRING NOT NULL,
  dashboard_id STRING NOT NULL,
  google_slides_template_id STRING NOT NULL COMMENT 'snapshot of template GSlides ID at generation time',
  user_prompt STRING,
  html_doc STRING NOT NULL,
  design_tokens STRING NOT NULL COMMENT 'JSON',
  theme_markdown STRING,
  status STRING NOT NULL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS {{catalog}}.{{schema}}.deck_revisions (
  id STRING NOT NULL,
  deck_id STRING NOT NULL,
  revision_no INT NOT NULL,
  html_doc STRING NOT NULL,
  trigger STRING NOT NULL,
  comment_note STRING,
  created_at TIMESTAMP
) USING DELTA;

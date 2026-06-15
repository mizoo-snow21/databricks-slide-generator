-- Add Google Slides re-export fields (run after 2026-05-07-editable-deck.sql).
-- Substitute {{catalog}} and {{schema}} with env values.

ALTER TABLE {{catalog}}.{{schema}}.decks ADD COLUMNS (
  gslides_file_id STRING COMMENT 'Last exported Google Slides presentation id',
  gslides_url STRING COMMENT 'Last exported Google Slides edit URL'
);

# Decisions

## Criteria template storage: DB-primary with YAML export/import — 2026-05-15
**What:** Criteria templates live in the DB (`CriteriaGroup` + `CriteriaVersion`). `config/criteria/*.yml` files are a seed library imported on first boot. The UI supports export-to-YAML (download) and import-from-YAML (upload → validate → save as new group or new version). The Pydantic criteria schema is the shared validation layer for the inline editor, import, and AI assistant.
**Why:** File-based templates in a mounted volume can't support CRUD, save-as, or version history without filesystem writes from the app. DB-primary keeps all state in one place; YAML import/export covers the offline-edit workflow.
**Alternatives considered:** Files-only (no CRUD without git), DB-only (no offline edit workflow).

## [Decision title] — YYYY-MM-DD
**What:** 
**Why:** 
**Alternatives considered:** 

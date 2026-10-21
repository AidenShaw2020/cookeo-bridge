# Changelog

## 0.3.0 — 2026-10-21

- First public Home Assistant repository package with icons, English/Czech documentation and MIT licensing.
- Private personal recipes: explicit PRIVATE visibility, PERSONAL device copy, per-account links, updates without duplicating the personal copy and read-back validation.
- Ingredient links per step, manufacturer program choices, optional stirring speed and program parameter validation.
- Personal recipe transfer verified on CE9821F0 by the owner; no cooking-start command is sent.
- Separate Shadow acceptance from cooker confirmation.
- Online cookbooks and updated Czech naming: Tvé online kuchařky.
- Recipe catalog, local library/import/export, ratings/reviews, local notes, themes and MQTT entities.
- HA MQTT service access enabled and migration without re-pairing documented.

- Separate local save, cloud save, cookbook assignment and cooker transfer; no implicit upload on assignment or send.
- Cloud visibility badges and immediate private/public controls for uploaded author sources; personal device copies remain private.
- Account-owned authorship, reordered header controls and simplified footer.
- Guarded cloud/local deletion preserves data if the API refuses; author deletion returned 403 in live testing.

# Changelog

## 0.4.2 — 2026-10-22

- Localize all 25 Infinity programs, plus known Touch/classic programs, in live telemetry, recipe steps and the editor using the interface language (English/Czech), independently of account locale.
- Show reported program duration separately from remaining time; expose duration through MQTT discovery. Derive remaining time from target minus reported elapsed time only during cooking when no explicit countdown is available.
- Clear stale timing values at phase/program transitions. Warm-up without reported timing stays unknown; progress is not converted into an ETA.

## 0.4.1 — 2026-10-22

- Clarify manual browser sign-in in the English/Czech UI and guides: retrieve the complete gsmoduser callback from the manufacturer return page source (Ctrl+U, Ctrl+F), not the address bar.

## 0.4.0 — 2026-10-22

- Distinguish authored recipes and imported personal adaptations in cards, details, editor and version-4 exports. Preserve original title/author/source and prevent relabelling imports as independent authorship.
- Remove the unrelated catalog-base picker. Imported recipes automatically use their original; new author recipes start from a blank local draft.
- Add an author review with native required-field checks, own-photo guidance, terms link and explicit submission confirmation. Cancel/review does not publish.
- Separate public author submission and its own private PERSONAL device variant, including moderation status, device readiness and incomplete-result protection.
- Keep photo failures retryable before the recipe POST; prevent duplicate roots after uncertain submission. Preserve legacy ownership bindings and protect them during incomplete deletion.
- Validate both workflows with mocked backend and English/Czech browser tests. No new public synthetic submission or cooker command was used in this release.

## 0.3.2 — 2026-10-21

- Recognize confirmed PERSONAL soft deletion: the lite API retains a DELETED record while the mobile endpoint returns 404. Both conditions are required before removing local ownership bindings.
- Avoid a duplicate DELETE when retrying an already deleted copy. A readable mobile recipe still fails closed.
- Verified one BE/nl personal-copy deletion: absent from the personal list, local recipe and published catalog source preserved. Authored-source deletion remains a separate, previously refused operation.

## 0.3.1 — 2026-10-21

- Separate native PERSONAL adaptation creation from explicit author publication. New personal saves require a compatible published catalog base; cancelling its selector makes no cloud write. A live BE/nl test verified PRIVATE + PERSONAL content, the unchanged catalog source and personal-list indexing with status PERSONAL; official mobile UI display remains unconfirmed.
- Private saves never create or update authored sources. A PRIVATE-access author record entered moderation in earlier testing; the author endpoint also ignored a requested PRIVATE status.
- Public author submission requires an own food photograph and reports moderation/correction separately from approved publication. The payload is tested with mocked responses; no synthetic public publication was performed.
- Prevent automatic duplicate creation after a lost response; protect catalog originals and scope ownership to the account/region.
- Preserve the previous visibility selection if a cloud change fails.
- Fix removal from online cookbooks by resolving variant IDs to top recipe IDs; live removal preserved the catalog original. Cookbook membership and author-record deletion use different API operations.

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

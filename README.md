# Cookeo Bridge

<p><img src="cookeo/logo.png" alt="Cookeo Bridge" width="400"></p>

A Home Assistant app/add-on with a recipe web interface, regional manufacturer account setup and MQTT entities for Cookeo. English and Czech interfaces; runs in Home Assistant OS, Docker or Python 3.12+.

[Český návod](README.cs.md) · [Setup and migration](cookeo/DOCS.md) · [Changelog](cookeo/CHANGELOG.md) · [MIT license](LICENSE)

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FAidenShaw2020%2Fcookeo-bridge)

## Why this project exists

A cooker bought for another distribution market can be absent from the app's product catalog in the owner's country. A mismatch between the cooker's languages, regional catalog and account context can prevent registration or everyday use through the local app.

This project started with a Moulinex Cookeo Infinity CE9821F0 bought for a French/Italian/Dutch distribution and used in the Czech Republic. The Czech My Tefal route failed, while the same manufacturer's account could register the cooker using the Belgian My Moulinex context. Cookeo Bridge provides that regional setup together with an English/Czech web interface and Home Assistant telemetry.

The cooker continues to use the manufacturer's cloud. No firmware change, DNS redirection or factory reset is required. The cooker menu retains its installed languages. Regional support still depends on the manufacturer's available catalog and account services.

## Features

- Manufacturer browser sign-in, selectable brand/country/account language, and refreshable encrypted sessions.
- Automatic discovery of cookers already linked to the selected cloud profile.
- Recipe search across languages, pagination, photos, authors, ratings, reviews and personal local notes.
- Local recipe editor with ingredients, per-step ingredient selection, cooking programs, durations, optional temperature and stirring speed.
- Imported personal adaptations with original-author attribution, and a separate full author-publication review with photo validation and moderation/device-copy status.
- Online cookbooks: create, rename, delete and add/remove recipes.
- Home Assistant MQTT discovery: cooking status, mode, program, recipe, step, remaining/elapsed time, progress, target temperature, firmware, errors and connectivity when reported by the device.
- Optional one-attempt Bluetooth provisioning for the verified CE9821F0. HA Bluetooth/proxy advertisement discovery helps find the device address; provisioning currently requires Bluetooth local to the app host.
- Automatic light/dark theme with manual override; English by default, Czech available.

## Install in Home Assistant OS

1. Add `https://github.com/AidenShaw2020/cookeo-bridge` under **Settings → Apps / Add-ons → App store → ⋮ → Repositories**, or use the badge above.
2. Install **Cookeo Bridge**. Home Assistant builds the container locally on `amd64` or `aarch64`.
3. Set the manufacturer's brand, country and account language under **Configuration**. These are separate from `ui_language`.
4. Start the app and select **Open Web UI**. Sign in on the manufacturer's website using your own account.
5. Configure MQTT, or let the app discover the installed Mosquitto service. Home Assistant must have its MQTT integration enabled for entities to appear.

For manual sign-in completion, obtain the `gsmoduser://tokens#...` callback **from the manufacturer's return page source** (`Ctrl+U` on a PC, then `Ctrl+F`), including the full part after `#`. Paste it into **Complete browser return → Callback URL**. The normal browser address-bar URL does not work. See [browser sign-in](cookeo/DOCS.md#browser-sign-in); do not share the callback tokens.

**Already registered? Sign in using the same account and the same regional context. Do not start pairing again.** See [migration](cookeo/DOCS.md#move-an-already-paired-cooker-to-home-assistant).

## Recipe lifecycle and privacy

The library distinguishes **Author recipe** (created from scratch) and **Personal adaptation** (imported from an online recipe). Kind and source references survive local edits and JSON export/import; a saved import cannot be relabelled as an independent authored recipe. Cards, details and the editor show the kind. Adaptations retain the original title/author and a link to the source.

### Import and adapt an online recipe

1. Open **Online recipes**, choose a recipe and **Save a copy to library**.
2. Edit the local ingredients, steps, servings or times. **Save** remains local.
3. **Save personal adaptation** creates/updates a private `PERSONAL` variant linked automatically to that imported original. There is no separate source-picker and the catalog original is not changed. The original market/language are retained in the adaptation payload; other regional combinations can still be refused by the provider and are not live-verified.
4. **Send to cooker** uses the current verified personal variant on an idle cooker. It does not upload edits or start cooking. **Assign online cookbook** only opens the selector for an existing uploaded copy.

Personal adaptations cannot enter the independent author-publication flow. Importing another person's recipe does not transfer its authorship. The signed-in account is the owner of the local copy; the original author is shown separately. Personal notes stay local.

### Create a new author recipe

1. Choose **New recipe**. Write your own title, ingredients, ingredient references per step and cooker programs. Save a local draft whenever you want; no unrelated catalog base is required.
2. Add your own photograph of the finished dish. Select **Review and publish**.
3. The review checks the manufacturer's observed form requirements: photograph, supported course, 1–99 servings, preparation time of at least one minute, ingredients assigned to steps, numeric ingredient quantities in the accepted range, step descriptions up to 1000 characters and at least one cooker program. Program parameters are validated against the selected model. Missing fields are listed before submission. Photo guidance and a link to the manufacturer's terms are shown.
4. Review the recipe/photo and explicitly confirm submission. Opening or cancelling the review makes no cloud write. The manufacturer can approve the recipe or request corrections; submission is not immediate public listing.

The author endpoint receives the full recipe and uploaded photograph. After it confirms a root, a separate private `PERSONAL` variant is prepared from **that owned author root**, never a random catalog recipe. Public moderation and device-copy readiness are separate states: transfer stays unavailable until the private variant is verified. If the author submission succeeds but the device copy is unavailable, the UI reports that distinction and preserves the author reference rather than submitting another root.

Badges distinguish private access, pending approval, corrections and approved publication. An already submitted author version can request private visibility; making it public again opens the publication review. This does not erase earlier moderation history. A lost creation response blocks automatic duplicate creation; a photo upload failure before the recipe POST remains retryable.

**Verification:** private PERSONAL creation, read-back and deletion were tested live in BE/nl, as was personal transfer earlier. The new complete author review, photo payload, publication/update and owned-root-to-PERSONAL flow are covered by mocked backend/browser tests; no new synthetic recipe was publicly submitted. Appearance in the official mobile UI and eventual approval remain unconfirmed. Earlier PRIVATE author records entered moderation, so PRIVATE access or anonymous 404 must not be presented as proof that an author record bypasses moderation.

**Cookbooks and recipe deletion are different operations.** Removing a catalog recipe from a cookbook only removes that membership; the catalog original remains. Cookbook deletion removes the collection, not its source recipes. Both operations were verified in the BE/nl profile. Version 0.3.1 resolves the variant identifier returned by cookbook search to its top recipe identifier before removal.

Deletion of a private `PERSONAL` adaptation was verified live in BE/nl. The cloud retains a lite `DELETED` record while the mobile endpoint returns 404 and the personal list no longer contains it. Version 0.3.2 recognizes that result and does not send another DELETE on retry. The local recipe and original catalog source were preserved. This is a provider soft deletion, not proof of physical erasure from its storage.

Deleting an owned authored source is a separate operation. The Android recipe DELETE request returned HTTP 403 for our private author test record; this does not imply a general account restriction on cookbook management. The UI verifies deletion and never reports a refusal as success. Deleting a linked local recipe requires removal of its owned cloud copies, so failure preserves the local content and bindings. Unlinked local recipes can be deleted normally.

Local export/import transfers content, not ownership bindings to existing cloud copies.

## Run without Home Assistant

```sh
docker compose up --build -d
```

Open `http://127.0.0.1:8098`. Data is stored in `.stack-data`. Print the local access key on your own terminal with:

```sh
docker compose exec cookeo python -c "from app.store import Store; s=Store('/data'); print(s.get('admin_token')); s.close()"
```

On Windows with Python 3.12+:

```powershell
./setup.ps1
./start.ps1
```

The native launcher opens the local web interface with its generated access key. Add `-Demo` for a local-only UI demonstration. If port 8098 is in use, stop the other development instance or choose another port.

For an isolated HA Core + MQTT development environment, see [development](docs/DEVELOPMENT.md). Your production Home Assistant is not restarted by these commands.

## Status and limitations

Experimental community software. Registration and personal-recipe transfer have been verified with **CE9821F0 / CMMF 7211419888 / firmware 1.8.3**, using My Moulinex BE/nl. Other cookers/markets need verification. Cloud telemetry is shown only when the device supplies it. The app distinguishes cloud acceptance from device confirmation; the cooker may load a recipe without emitting the confirmation event, so check its display.

An Internet connection and functioning manufacturer services are required for cloud features. This app does not install firmware or add languages to the cooker. Recipe transfer does not start heating. New provisioning supports only the verified CE9821F0 and does not implement a remote GATT pairing path through HA Bluetooth proxies.

Keep app data and Home Assistant backups private. OAuth tokens are encrypted in app storage, with the encryption key in the same private data folder. Standalone access is bound to loopback by default; HA uses authenticated ingress. Do not include sessions or callback URLs in GitHub issues.

## License and acknowledgements

MIT; see [LICENSE](LICENSE) and [third-party attribution](NOTICE.md).

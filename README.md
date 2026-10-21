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
- Personal recipe adaptations with an explicit catalog source, read-back validation and ownership tracking; separate public author submission with a food photograph and moderation status.
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

**Already registered? Sign in using the same account and the same regional context. Do not start pairing again.** See [migration](cookeo/DOCS.md#move-an-already-paired-cooker-to-home-assistant).

## Recipe lifecycle and privacy

| Action | Result |
| --- | --- |
| Save | Saves only the local library entry. |
| Save to cloud | Creates or updates a private `PERSONAL` adaptation. For a new copy, explicitly choose a compatible published recipe as its base. Cancelling the selector creates no cloud record. |
| Assign online cookbook | Opens a cookbook selector for an existing cloud copy. Opening/cancelling does not upload or publish anything. |
| Send to cooker | Verifies and loads the current saved personal copy on an idle cooker. Does not upload local edits or start cooking. |

**Personal saving and public submission use different API workflows.** The manufacturer's author form requests a complete recipe and photograph and does not offer a private/public choice. Its creation endpoint ignored a requested `PRIVATE` status in our live test. An earlier authored source with private access entered moderation and became `TO_BE_CORRECTED`; anonymous 404 proved restricted access, not absence of moderation.

The revised private path creates only a native `PERSONAL` adaptation of a published catalog recipe in the account's market/language. It does not create or update an authored source, copy an unrelated dish photograph or modify the catalog original. A base already linked to another local personal recipe is rejected. A lost creation response is retained for inspection rather than automatically creating another copy. **A live BE/nl test created one PRIVATE + PERSONAL copy, verified its ingredients/steps and found it in the personal-recipe search using status PERSONAL. The published source stayed unchanged and no authored record was created. Appearance in the official mobile UI has not been confirmed.**

Choosing **Public** for an uploaded recipe explicitly submits an author version with your own food photograph. The personal device copy remains private. The badge distinguishes submission/pending approval, correction and approved publication; submitting does not mean the recipe is immediately listed for everyone. The photo upload/publication payload is covered by mocked tests and has not been submitted live as part of this fix. Choosing **Private** requests private access for the owned author version; it does not erase previous moderation history.

The author comes from the signed-in account. Notes remain local. Private adaptations currently do not upload their local photograph. Importing a recipe does not grant ownership of its catalog source. Export/import transfers content, not existing cloud ownership bindings: choose an unused base for a new personal copy rather than replacing an adaptation created in another installation.

**Cookbooks and recipe deletion are different operations.** Removing a catalog recipe from a cookbook only removes that membership; the catalog original remains. Cookbook deletion removes the collection, not its source recipes. Both operations were verified in the BE/nl profile. Version 0.3.1 resolves the variant identifier returned by cookbook search to its top recipe identifier before removal.

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

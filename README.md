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
- Private-by-default cloud recipes, visibility controls, owned-copy tracking, editing, read-back validation and transfer through a private `PERSONAL` adaptation.
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
| Save to cloud | Saves the current recipe using the selected visibility, private by default. |
| Assign online cookbook | Opens a cookbook selector for an existing cloud copy. Opening/cancelling does not upload or publish anything. |
| Send to cooker | Verifies and loads the current saved cloud copy on an idle cooker. Does not save unpublished local edits or start cooking. |

Badges show local-only, cloud/private, cloud/public and unsaved content changes. Opening a recipe verifies its cloud status. The author is taken from the signed-in account; its nickname appears in the top bar.

For a new recipe, visibility is a draft choice until **Save to cloud**. For an already uploaded recipe, changing **Private / Public** immediately updates its authored cloud source. The device-readable `PERSONAL` adaptation remains private. Public visibility is a publication request; catalog indexing and any moderation remain controlled by the manufacturer. No community publication was performed during release testing.

Private copies are checked using authenticated read-back and an anonymous read expected to return 404. Contents and cooker parameters are checked before transfer. Editing an imported online recipe never overwrites its original.

**Cloud deletion limitation:** the exact recipe DELETE route in the supplied Android APK returned HTTP 403 for our private author test record. The UI provides a deletion attempt and verifies removal; it never reports a refused deletion as success. Deleting a linked local recipe requires successful deletion of its owned cloud copies, so a refusal preserves the local recipe and links for retry. Cloud-only deletion preserves local content. Unlinked local entries can be deleted normally. Do not assume deletion permissions are available in every profile.

Photos and personal notes currently remain local. Local export/import transfers content, not ownership bindings to existing cloud copies.

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

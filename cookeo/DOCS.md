# Configuration and migration

## Configuration

| Option | Purpose |
| --- | --- |
| `ui_language` | Web interface language: `en` (default) or `cs`. |
| `brand` | Manufacturer account/application context: `moulinex` or `tefal`. |
| `country` | Two-letter manufacturer market, e.g. `BE`. |
| `language` | Manufacturer account/recipe language, e.g. `nl`. Independent of the web interface. |
| `mqtt_host`, `mqtt_port` | Local Home Assistant MQTT broker. Leave host empty to discover the Supervisor MQTT service. |
| `mqtt_username`, `mqtt_password` | Broker credentials, if configured manually. |
| `mqtt_tls` | TLS for the MQTT broker. |

User passwords for the manufacturer account are entered on the manufacturer's sign-in page, not into add-on configuration. The add-on stores the returned OAuth session encrypted in its private data directory.

## Browser sign-in

1. Choose the correct brand, country and account language before signing in.
2. Open **Sign in with manufacturer** in the web interface and sign in with your existing email/password.
3. The provider returns a `gsmoduser://tokens#...` callback intended for its mobile apps. If your browser cannot open that protocol, use **Complete browser return** in Cookeo Bridge.
4. Copy the complete callback from the return page's source or browser console into the masked callback field. A normal `https://account.groupeseb.com/...` page address is not the callback. State and nonce must match the current login attempt.
5. Never post the callback or its tokens into issues or chat. If the login attempt expires, start a new one.

The callback capture depends on the manufacturer's login page; platform changes can affect it. HA ingress uses your HA authentication, so the standalone local access key is not needed in HA.

## Move an already-paired cooker to Home Assistant

The pairing belongs to your manufacturer's cloud account and regional profile. A fresh installation can discover that binding after account sign-in. Copying tokens or repeating Bluetooth pairing is unnecessary.

For the verified imported CE9821F0 setup:

```yaml
ui_language: cs
brand: moulinex
country: BE
language: nl
```

Use the same email/password as the existing manufacturer account, even if you originally created it in My Tefal. Select My Moulinex BE/nl because that is where this cooker was successfully registered. A CZ/tefal context is a different profile perimeter and may show no linked cooker.

Stop the old PC/Docker bridge before starting the HA app, particularly if both use the same MQTT broker. Open the HA app, sign in, and let the linked device load. Do not open the pairing wizard, factory-reset the cooker or remove it from the manufacturer's account.

Export local recipes from the previous **My recipes** screen and import them into the new installation. This transfers recipe content, not OAuth sessions, remote-copy bindings or separate personal notes on online recipes. On first upload of an imported local recipe, explicitly select an unused compatible catalog base for the new personal copy. Cloud cookbooks and the cooker registration remain on the manufacturer's account.

## MQTT and entities

Install/configure the MQTT integration in Home Assistant. If using the Mosquitto app, leave `mqtt_host` empty for service discovery; otherwise enter the broker and credentials explicitly. State topics use `cookeo_bridge/`, discovery uses `homeassistant/`.

Published entities are read-only telemetry. Missing values remain unknown/unavailable. The displayed temperature is the target reported by the cooker, not a measured food temperature. Do not assume every model reports every field.

## Recipes and cookbooks

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

## Optional new pairing

Only CE9821F0 provisioning is verified. This is not needed for an already linked cooker. Choose the appropriate manufacturer profile, sign in, enable pairing on the cooker and run one explicit attempt. Enter Wi-Fi credentials only in the local form. Enter the fresh cooker code on the manufacturer's website and confirm acceptance in the add-on.

HA Bluetooth/proxy discovery lists advertisements and helps choose an address. The provisioning connection currently uses the app host's local Bluetooth adapter through BlueZ/D-Bus; remote GATT provisioning through HA proxies is not implemented. Network and cloud data retain the original SEB endpoint.

## Storage and troubleshooting

The HA app stores its SQLite library, encryption key and encrypted settings in `/data`; include the app in your HA backups. Backups contain credentials and must be kept private. Account-region changes require disconnecting the local session first; this does not delete the cooker registration.

If no cooker appears, check account/brand/market/language before pairing. If cloud sign-in works but entities do not appear, check MQTT and HA's MQTT integration. If the device does not confirm a recipe, inspect its display; never interpret an MQTT publish acknowledgement alone as a successful load.

The UI and Docker image have been tested independently of Supervisor, with HA MQTT discovery verified in an isolated HA Core environment. Installation through a production HA OS Supervisor is a separate deployment check. `aarch64` is offered for local builds but needs physical-host verification.

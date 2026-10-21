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

Export local recipes from the previous **My recipes** screen and import them into the new installation. This transfers recipe content, not OAuth sessions, remote-copy bindings or separate personal notes on online recipes. On first upload of an imported local recipe, the new installation creates its own private copy. Cloud cookbooks and the cooker registration remain on the manufacturer's account.

## MQTT and entities

Install/configure the MQTT integration in Home Assistant. If using the Mosquitto app, leave `mqtt_host` empty for service discovery; otherwise enter the broker and credentials explicitly. State topics use `cookeo_bridge/`, discovery uses `homeassistant/`.

Published entities are read-only telemetry. Missing values remain unknown/unavailable. The displayed temperature is the target reported by the cooker, not a measured food temperature. Do not assume every model reports every field.

## Recipes and cookbooks

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

## Optional new pairing

Only CE9821F0 provisioning is verified. This is not needed for an already linked cooker. Choose the appropriate manufacturer profile, sign in, enable pairing on the cooker and run one explicit attempt. Enter Wi-Fi credentials only in the local form. Enter the fresh cooker code on the manufacturer's website and confirm acceptance in the add-on.

HA Bluetooth/proxy discovery lists advertisements and helps choose an address. The provisioning connection currently uses the app host's local Bluetooth adapter through BlueZ/D-Bus; remote GATT provisioning through HA proxies is not implemented. Network and cloud data retain the original SEB endpoint.

## Storage and troubleshooting

The HA app stores its SQLite library, encryption key and encrypted settings in `/data`; include the app in your HA backups. Backups contain credentials and must be kept private. Account-region changes require disconnecting the local session first; this does not delete the cooker registration.

If no cooker appears, check account/brand/market/language before pairing. If cloud sign-in works but entities do not appear, check MQTT and HA's MQTT integration. If the device does not confirm a recipe, inspect its display; never interpret an MQTT publish acknowledgement alone as a successful load.

The UI and Docker image have been tested independently of Supervisor, with HA MQTT discovery verified in an isolated HA Core environment. Installation through a production HA OS Supervisor is a separate deployment check. `aarch64` is offered for local builds but needs physical-host verification.

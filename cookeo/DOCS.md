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
4. **For manual completion, obtain the callback from the manufacturer's return page source after signing in.** On a PC, open **View page source** (`Ctrl+U`), then use `Ctrl+F` to find `gsmoduser://tokens#`. Copy the entire link, including everything after `#`, without surrounding quotes.
5. Paste it into Cookeo Bridge's masked **Callback URL** field and save. The normal `https://account.groupeseb.com/...` address from the browser address bar will not work. State and nonce must match the current login attempt.
6. Never post the callback or its tokens into issues or chat. If the login attempt expires, start a new one.

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

Export local recipes from the previous **My recipes** screen and import them into the new installation. This transfers recipe content, not OAuth sessions, remote-copy bindings or separate personal notes on online recipes. JSON import preserves kind and provenance, but does not recover ownership bindings to existing remote variants. Keep a protected full data backup if those bindings must move between installations; do not repeatedly create adaptations of the same original to recover a lost binding. Cloud cookbooks and the cooker registration remain on the manufacturer's account.

## MQTT and entities

Install/configure the MQTT integration in Home Assistant. If using the Mosquitto app, leave `mqtt_host` empty for service discovery; otherwise enter the broker and credentials explicitly. State topics use `cookeo_bridge/`, discovery uses `homeassistant/`.

Published entities are read-only telemetry. Missing values remain unknown/unavailable. The displayed temperature is the target reported by the cooker, not a measured food temperature. Do not assume every model reports every field.

## Recipes and cookbooks

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

## Optional new pairing

Only CE9821F0 provisioning is verified. This is not needed for an already linked cooker. Choose the appropriate manufacturer profile, sign in, enable pairing on the cooker and run one explicit attempt. Enter Wi-Fi credentials only in the local form. Enter the fresh cooker code on the manufacturer's website and confirm acceptance in the add-on.

HA Bluetooth/proxy discovery lists advertisements and helps choose an address. The provisioning connection currently uses the app host's local Bluetooth adapter through BlueZ/D-Bus; remote GATT provisioning through HA proxies is not implemented. Network and cloud data retain the original SEB endpoint.

## Storage and troubleshooting

The HA app stores its SQLite library, encryption key and encrypted settings in `/data`; include the app in your HA backups. Backups contain credentials and must be kept private. Account-region changes require disconnecting the local session first; this does not delete the cooker registration.

If no cooker appears, check account/brand/market/language before pairing. If cloud sign-in works but entities do not appear, check MQTT and HA's MQTT integration. If the device does not confirm a recipe, inspect its display; never interpret an MQTT publish acknowledgement alone as a successful load.

The UI and Docker image have been tested independently of Supervisor, with HA MQTT discovery verified in an isolated HA Core environment. Installation through a production HA OS Supervisor is a separate deployment check. `aarch64` is offered for local builds but needs physical-host verification.

### Program names and timing

Program names follow the interface language, including the live dashboard, recipe steps and program selector. All 25 programs returned by the Infinity catalog are mapped by stable ID; unknown future IDs retain the manufacturer's label.

Program duration is the reported DURATION parameter in seconds, separately from remaining time. Remaining time uses the appliance countdown, or target minus reported elapsed time during cooking only. No warm-up ETA is inferred from percentages or wall-clock timestamps. During the live warm-up check, both the cooking event and shadow omitted timing and target parameters, so both time fields correctly remained unknown.

# Development

The same Python server runs natively, in Docker and behind HA ingress. Use separate runtime folders for development. No production HA restart is required for web development.

## Native Python

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r cookeo/requirements.txt
cd cookeo
python -m app.server --data ../.dev-data --open-browser
```

Windows users can run `setup.ps1` and `start.ps1`. `start.ps1 -Demo` disables cloud operations. The standalone API requires the generated local key; the launcher passes it using a browser fragment and removes it from the address bar after loading.

## Docker

```sh
docker compose up --build -d
```

Changes to HTML/JavaScript/CSS are directly served by the native process; refresh the browser. Restart the native process after Python changes. Rebuild the container after changing packaged files.

## Isolated Home Assistant Core and MQTT

```sh
docker compose -f compose.test.yaml up -d
```

This creates an independent HA Core instance on `http://127.0.0.1:18123` and a test broker on `127.0.0.1:18884`. Data is stored in `.ha-data`. Configure the test HA MQTT integration to connect to host `mqtt`, port `1883`, without credentials. Point a native Cookeo Bridge at `127.0.0.1:18884`.

The development broker allows anonymous access and is bound to loopback on the host. Do not use it as a production broker. If the ports are already occupied, choose different host ports; keep production and test data directories separate.

## Tests

```sh
python -m unittest discover -s tests -p 'test_*.py'
node tests/test_recipe_detail.cjs
node tests/test_recipe_media.cjs
python tools/check_package.py
```

Unit tests use temporary stores, mocked cloud calls and a local test WebSocket. They never sign in, publish a community recipe, pair a cooker or start cooking. Live tests must use the owner's own account and separate neutral test recipes; never publish personal recipes as a test shortcut.

The public package excludes private captures, firmware experiments and user data. CI runs the tests and a container demo smoke test. HA OS Supervisor installation and real BLE provisioning require their own host-level verification.

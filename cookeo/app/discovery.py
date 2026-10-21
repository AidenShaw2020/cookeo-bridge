"""Bounded advertisement discovery; no GATT connections or provisioning writes."""
import asyncio
import os
import re
import sys
import time
from urllib.parse import urlsplit, urlunsplit
import aiohttp


def ha_connection(store):
    if os.environ.get('SUPERVISOR_TOKEN'):
        return 'ws://supervisor/core/websocket', os.environ['SUPERVISOR_TOKEN']
    config = store.get('ha', {})
    url = config.get('url', '').strip().rstrip('/')
    token = config.get('token', '')
    if not url or not token:
        raise ValueError('Mimo HA nejdřív v nastavení Home Assistant vyplň jeho URL a administrátorský přístupový token. V doplňku HA OS se přístup nastaví automaticky.')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Zadej základní HTTP(S) adresu Home Assistant bez přihlašovacích údajů.')
    return urlunsplit(('wss' if parsed.scheme == 'https' else 'ws', parsed.netloc,
                       parsed.path.rstrip('/') + '/api/websocket', '', '')), token


def candidate(info, source):
    address = str(info.get('address', '')).upper()
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', address):
        return None
    name = str(info.get('name') or 'Nepojmenované BLE zařízení')[:100]
    uuids = [str(v).lower() for v in info.get('service_uuids', [])]
    likely = any(v in name.lower() for v in ('cookeo', 'moulinex', 'seb')) or any(v.startswith('47656e65-7269-63') for v in uuids)
    rssi = info.get('rssi')
    if not isinstance(rssi, (int, float)) or not -127 <= rssi <= 20:
        rssi = None
    return {'address': address, 'name': name, 'rssi': rssi, 'candidate': likely,
            'source': source, 'connectable': bool(info.get('connectable', True))}


async def ha_scan(store, seconds=8):
    url, token = ha_connection(store)
    devices = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=seconds + 15), trust_env=False) as session:
            async with session.ws_connect(url, max_msg_size=2_000_000, autoclose=True) as ws:
                if (await ws.receive_json(timeout=8)).get('type') != 'auth_required':
                    raise ValueError('HA nevrátil očekávaný požadavek na přihlášení.')
                await ws.send_json({'type': 'auth', 'access_token': token})
                if (await ws.receive_json(timeout=8)).get('type') != 'auth_ok':
                    raise ValueError('HA odmítl přihlášení. Pro Bluetooth je potřeba administrátorský účet.')
                await ws.send_json({'id': 1, 'type': 'bluetooth/subscribe_advertisements'})
                result = await ws.receive_json(timeout=8)
                if result.get('type') != 'result' or not result.get('success'):
                    raise ValueError('HA neposkytuje Bluetooth skenování. Zkontroluj integraci Bluetooth a oprávnění administrátora.')
                deadline = asyncio.get_running_loop().time() + seconds
                while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
                    try:
                        message = await ws.receive_json(timeout=remaining)
                    except asyncio.TimeoutError:
                        break
                    event = message.get('event') or {}
                    for info in event.get('add', [])[:500]:
                        stamp = info.get('time')
                        if isinstance(stamp, (int, float)) and time.time() - stamp > 120:
                            continue
                        value = candidate(info, 'ha')
                        if value and len(devices) < 200:
                            devices[value['address']] = value
                    for info in event.get('remove', []):
                        devices.pop(str(info.get('address', '')).upper(), None)
    except (aiohttp.ClientError, OSError, asyncio.TimeoutError):
        raise ValueError('K Bluetooth API Home Assistant se nelze připojit. Ověř adresu, token a dostupnost HA.') from None
    return sorted(devices.values(), key=lambda d: (not d['candidate'], -(d['rssi'] or -127)))


async def local_scan(seconds=8):
    from bleak import BleakScanner
    devices = {}
    def detected(device, advertisement):
        value = candidate({'address': device.address, 'name': advertisement.local_name or device.name,
                           'rssi': advertisement.rssi, 'service_uuids': advertisement.service_uuids}, 'local')
        if value and len(devices) < 200:
            devices[value['address']] = value
    try:
        async with BleakScanner(detection_callback=detected, scanning_mode='passive' if sys.platform=='win32' else 'active'):
            await asyncio.sleep(seconds)
    except Exception:
        raise ValueError('Místní Bluetooth není dostupné. Zkontroluj adaptér nebo použij vyhledávání přes HA.') from None
    return sorted(devices.values(), key=lambda d: (not d['candidate'], -(d['rssi'] or -127)))

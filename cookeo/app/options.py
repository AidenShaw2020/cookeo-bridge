"""Apply changed Supervisor options without overwriting later web settings."""
import json
import re
from pathlib import Path


def apply_options(store):
    path = Path(store.folder) / 'options.json'
    if not path.exists():
        return
    values = json.loads(path.read_text(encoding='utf-8'))
    previous = store.get('addon_options_previous', {})
    selection = {key: values.get(option, default) for key, option, default in (
        ('brand', 'brand', 'moulinex'), ('market', 'country', 'BE'), ('lang', 'language', 'nl'))}
    old_selection = {key: previous.get(option) for key, option in (
        ('brand', 'brand'), ('market', 'country'), ('lang', 'language'))}
    store.set('configuration_error', None)
    ui_language = values.get('ui_language', 'en')
    if ui_language != previous.get('ui_language') and ui_language in ('en', 'cs'):
        store.set('ui_language', ui_language)
    if selection != old_selection:
        if selection['brand'] not in ('moulinex', 'tefal') or not re.fullmatch('[A-Z]{2}', selection['market']) or not re.fullmatch('[a-z]{2}', selection['lang']):
            store.set('configuration_error', 'Neplatná značka, země nebo jazyk v Konfiguraci doplňku.')
        elif store.get('tokens') and selection != store.get('selection'):
            store.set('configuration_error', 'Změna profilu z Konfigurace čeká: nejdřív v Účet a jazyk odpoj místní relaci a ulož nový region. Hrnec zůstává registrovaný.')
        else:
            store.set('selection', selection)
    mqtt_keys = {'host':'mqtt_host', 'port':'mqtt_port', 'username':'mqtt_username', 'password':'mqtt_password', 'tls':'mqtt_tls'}
    if any(values.get(option) != previous.get(option) for option in mqtt_keys.values()):
        mqtt = {key: values.get(option, {'port':1883, 'tls':False}.get(key,'')) for key,option in mqtt_keys.items()}
        if mqtt['host']:
            store.set('mqtt', mqtt)
    store.set('addon_options_previous', values)

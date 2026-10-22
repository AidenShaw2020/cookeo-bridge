"""Localized appliance programs; IDs stay independent of cloud account locale."""
import json
from pathlib import Path

PROGRAM_NAMES = json.loads((Path(__file__).parent / 'web/programs.json').read_text(encoding='utf-8'))


def program_name(key, fallback=None, language='en'):
    return PROGRAM_NAMES.get(key, {}).get(language) or fallback or key or None

"""Validate install metadata and guard against shipping runtime/private artifacts."""
from pathlib import Path
import json
import struct
import yaml

root=Path(__file__).resolve().parents[1]
repository=yaml.safe_load((root/'repository.yaml').read_text(encoding='utf-8'))
config=yaml.safe_load((root/'cookeo/config.yaml').read_text(encoding='utf-8'))
assert repository['url']=='https://github.com/AidenShaw2020/cookeo-bridge'
assert config['slug']=='cookeo_bridge' and config['ingress'] and config['init'] is False
assert set(config['arch'])=={'amd64','aarch64'}
assert config['hassio_api'] and config['homeassistant_api'] and config['hassio_role']=='default'
assert set(config['options'])==set(config['schema'])
for name in ('README.md','README.cs.md','LICENSE','NOTICE.md','cookeo/README.md','cookeo/DOCS.md','cookeo/CHANGELOG.md'):
    assert (root/name).is_file(),name
for name in ('icon.png','logo.png'):
    raw=(root/'cookeo'/name).read_bytes()
    assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    width,height=struct.unpack('>II',raw[16:24])
    assert width>0 and height>0
    if name=='icon.png':assert width==height
for lang in ('en','cs'):
    strings=json.loads((root/'cookeo/translations'/f'{lang}.json').read_text(encoding='utf-8'))
    assert set(strings['configuration'])==set(config['schema'])
# Only inspect distributable directories; developer runtime folders are ignored.
for folder in ('cookeo','tests','tools','.github','dev-ha','dev-mqtt'):
    for path in (root/folder).rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:continue
        assert path.suffix.lower() not in ('.enc','.key','.pcap','.pcapng','.apk','.xapk','.sqlite','.sqlite3','.log'),path
print('Repository metadata, translations, icons and distribution files passed.')

"""Validate publication provenance without changing generated data or receipts."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

FIELDS = (
    'api_url', 'api_version', 'generator_name', 'generator_version',
    'data_source', 'data_version', 'patch_source', 'patch_version',
)


def validate_generation_metadata(database, source, output_base, version, expected):
    """Require the DB and both data formats to bind the same frozen inputs."""
    if version in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', version):
        raise ValueError('Invalid API version for generation metadata')
    if set(expected) != set(FIELDS) or any(
        not isinstance(expected[key], str) or not expected[key].strip()
        for key in FIELDS
    ):
        raise ValueError('Missing generation metadata bindings')
    official = (Path(source) / 'unity' / '.version').read_text('utf-8').strip()
    if not re.fullmatch(r'[0-9]{14}', official):
        raise ValueError('Invalid frozen official configuration version')
    if expected['data_version'] != official or expected['api_version'] != version:
        raise ValueError('Generation metadata bindings differ from frozen source')
    if not re.fullmatch(r'[0-9a-f]{40}', expected['patch_version']):
        raise ValueError('Generation metadata requires a full patch SHA')
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        try:
            rows = connection.execute('SELECT ' + ','.join(FIELDS) + ' FROM api_metadata').fetchall()
        except sqlite3.OperationalError as error:
            raise ValueError('Generation metadata table or required columns missing') from error
    if len(rows) != 1:
        raise ValueError('Generation metadata must contain exactly one DB row')
    check = [('database', dict(zip(FIELDS, rows[0])))]
    for kind in ('data', 'sharded_data'):
        path = Path(output_base) / version / kind / 'metadata.json'
        check.append((kind, json.loads(path.read_text('utf-8'))))
    for label, actual in check:
        mismatches = [key for key in FIELDS if actual.get(key) != expected[key]]
        if mismatches:
            raise ValueError(f'Generation metadata mismatch in {label}: {", ".join(mismatches)}')
    return {'data_version': official, 'patch_version': expected['patch_version'], 'formats': 2}

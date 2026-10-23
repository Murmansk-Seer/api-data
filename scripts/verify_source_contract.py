"""Reject missing generated records before committing or publishing api-data."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import hashlib
import os
import re
import shutil


def validate_source_references(source):
    root = Path(source) / 'unity'
    def load(name):
        return json.loads((root / name).read_text(encoding='utf8'))
    # Preserve the existing canonical-pet domain; later sections are battle copies.
    pets = set()
    for row in load('monsters.json')['monsters']['monster']:
        if row['id'] > 9999:
            break
        pets.add(row['id'])
    if not pets:
        raise ValueError('monsters.json: no official pet records')
    valid = {'soulmark': set(), 'glossary_entry': set()}
    missing = {}
    for resource, filename, field, container in (
        ('soulmark', 'effectIcon.json', 'pet_id', 'effect'),
        ('glossary_entry', 'effectDes.json', 'monster', 'item'),
    ):
        for row in load(filename)['root'][container]:
            raw = row[field]
            ids = raw if field == 'pet_id' else (list(map(int, raw.split(','))) if raw and raw != '0' else [])
            for pet_id in ids:
                if type(pet_id) is not int or pet_id <= 0:
                    raise ValueError(f'{filename}: id={row["id"]}, invalid pet ID={pet_id!r}')
                if pet_id in pets:
                    valid[resource].add((row['id'], pet_id))
                else:
                    missing[(resource, row['id'], pet_id)] = (filename, field, row)
    print(f'Official pet references inspected: {len(missing)} require lossless preservation')
    return pets, valid, missing


def validate_reference_preservation(db, source):
    pets, valid, expected = validate_source_references(source)
    actual_pets = {row[0] for row in db.execute('SELECT id FROM pet')}
    if actual_pets != pets:
        raise ValueError('Generated pet IDs differ from official source; no fabricated or omitted pets allowed')
    for resource, table, owner_column in (
        ('soulmark', 'petsoulmarklink', 'soulmark_id'),
        ('glossary_entry', 'petglossaryentrylink', 'glossary_entry_id'),
    ):
        actual = set(db.execute(f'SELECT {owner_column}, pet_id FROM {table}'))
        if actual != valid[resource]:
            raise ValueError(f'{resource}: valid pet associations do not exactly match official source')
    retained = set()
    for resource, owner, target, filename, field, payload, digest, reason in db.execute(
        'SELECT owner_resource, owner_id, target_pet_id, source_file, source_field, source_json, source_sha256, reason FROM unresolved_pet_reference'
    ):
        key = (resource, owner, target)
        if key not in expected or key in retained:
            raise ValueError(f'Unexpected or duplicate preserved reference: {key!r}')
        expected_file, expected_field, raw = expected[key]
        if (filename, field, reason) != (expected_file, expected_field, 'target_missing') or json.loads(payload) != raw:
            raise ValueError(f'Preserved original source differs: {key!r}')
        if hashlib.sha256(payload.encode()).hexdigest() != digest:
            raise ValueError(f'Preserved source SHA256 mismatch: {key!r}')
        if db.execute(f'SELECT 1 FROM {resource} WHERE id=?', (owner,)).fetchone() is None:
            raise ValueError(f'Preserved reference owner is missing: {key!r}')
        retained.add(key)
    if retained != set(expected):
        raise ValueError(f'Missing lossless reference evidence: {sorted(set(expected)-retained)!r}')
    print(f'Exact source coverage: resolved edges + {len(retained)} preserved edges; no fabricated pets')


def prepare_reference_output(base, version):
    """Remove only stale generated evidence URLs, never other resources or Releases."""
    if version in ('.', '..') or re.fullmatch(r'[A-Za-z0-9_.-]+', version) is None:
        raise ValueError('Invalid API version for generated reference output')
    root = Path(base).resolve()
    targets = [root / version / kind / 'unresolved_pet_reference' for kind in ('data', 'sharded_data')]
    for path in targets:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Unsafe generated reference output path')
    for path in targets:
        if path.exists():
            shutil.rmtree(path)


def validate_source_sets(database, source):
    with closing(sqlite3.connect(database)) as db:
        for table, filename, keys in (
            ('skill', 'moves.json', ('root', 'moves', 'move')),
            ('factor', 'fragment.json', ('root', 'fragment')),
        ):
            rows = json.loads((Path(source) / 'unity' / filename).read_text(encoding='utf8'))
            for key in keys:
                rows = rows[key]
            expected = {row['id'] for row in rows}
            actual = {row[0] for row in db.execute(f'SELECT id FROM {table}')}
            if not expected or expected != actual:
                raise ValueError(f'{table} source ID mismatch: missing={sorted(expected-actual)[:20]}, extra={sorted(actual-expected)[:20]}')
            print(f'{table}: {len(actual)} IDs exactly match official source')
        errors = db.execute('PRAGMA foreign_key_check').fetchall()
        if errors:
            groups = Counter((row[0], row[2]) for row in errors)
            raise ValueError(f'Foreign key violations: total={len(errors)}, groups={dict(groups)!r}, first={errors[:20]!r}')
        validate_reference_preservation(db, source)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--prepare-reference-output', action='store_true')
    parser.add_argument('--output-base', type=Path, default=Path('data'))
    parser.add_argument('--api-version', default=os.environ.get('SOLARIS_API_VERSION', 'v1'))
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    if args.source_only:
        validate_source_references(args.source)
        if args.prepare_reference_output:
            prepare_reference_output(args.output_base, args.api_version)
    elif args.database is None:
        parser.error('--database is required unless --source-only is used')
    else:
        validate_source_sets(args.database, args.source)


if __name__ == '__main__':
    main()

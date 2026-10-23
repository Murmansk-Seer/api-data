"""Reject missing generated records before committing or publishing api-data."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3


def validate_source_references(source):
    root = Path(source) / 'unity'
    def load(name):
        return json.loads((root / name).read_text(encoding='utf8'))
    pets = {row['id'] for row in load('monsters.json')['monsters']['monster'] if row['id'] < 10000}
    if not pets:
        raise ValueError('monsters.json: no official pet records')
    errors = []
    for row in load('effectIcon.json')['root']['effect']:
        for pet_id in row['pet_id']:
            if pet_id not in pets:
                errors.append(f'effectIcon.json: id={row["id"]}, field=pet_id, missing pet={pet_id}')
    for row in load('effectDes.json')['root']['item']:
        raw = row['monster']
        for pet_id in (map(int, raw.split(',')) if raw and raw != '0' else ()):
            if pet_id not in pets:
                errors.append(f'effectDes.json: id={row["id"]}, field=monster, missing pet={pet_id}')
    if errors:
        raise ValueError('Official source references are inconsistent: ' + '; '.join(errors))
    print('Official pet source references validated before analysis')


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    if args.source_only:
        validate_source_references(args.source)
    elif args.database is None:
        parser.error('--database is required unless --source-only is used')
    else:
        validate_source_sets(args.database, args.source)


if __name__ == '__main__':
    main()

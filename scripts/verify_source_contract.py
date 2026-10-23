"""Reject missing generated records before committing or publishing api-data."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3


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
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    validate_source_sets(args.database, args.source)


if __name__ == '__main__':
    main()

import json
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from scripts.verify_source_contract import validate_source_sets, validate_source_references


class SourceContract(unittest.TestCase):
    def test_real_dangling_pet_references_fail_before_analysis_without_mutation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'unity').mkdir()
            source = {
                'monsters.json': {'monsters': {'monster': [{'id': 4542}]}},
                'effectIcon.json': {'root': {'effect': [{'id': 1753, 'pet_id': [4543]}, {'id': 769, 'pet_id': []}]}},
                'effectDes.json': {'root': {'item': [{'id': 117, 'monster': '4543,4542'}]}},
            }
            for name, data in source.items():
                (root / 'unity' / name).write_text(json.dumps(data))
            before = {p.name: p.read_bytes() for p in (root / 'unity').iterdir()}
            with self.assertRaisesRegex(ValueError, r'effectIcon.json: id=1753.*missing pet=4543.*effectDes.json: id=117.*missing pet=4543'):
                validate_source_references(root)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'unity').iterdir()})
            source['monsters.json']['monsters']['monster'].append({'id': 4543})
            (root / 'unity/monsters.json').write_text(json.dumps(source['monsters.json']))
            validate_source_references(root)

    def test_complete_ids_and_missing_row(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'unity').mkdir()
            (root / 'unity/moves.json').write_text(json.dumps({'root': {'moves': {'move': [{'id': 29481}, {'id': 38595}]}}}))
            (root / 'unity/fragment.json').write_text(json.dumps({'root': {'fragment': [{'id': 2400001}]}}))
            database = root / 'db.sqlite'
            with closing(sqlite3.connect(database)) as db:
                db.executescript('CREATE TABLE skill(id INTEGER); INSERT INTO skill VALUES(29481),(38595); CREATE TABLE factor(id INTEGER); INSERT INTO factor VALUES(2400001);')
            validate_source_sets(database, root)
            with closing(sqlite3.connect(database)) as db:
                db.execute('DELETE FROM skill WHERE id=29481')
                db.commit()
            with self.assertRaisesRegex(ValueError, 'skill source ID mismatch'):
                validate_source_sets(database, root)

    def test_dangling_reference_blocks_publication_even_with_complete_ids(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'unity').mkdir()
            (root / 'unity/moves.json').write_text(json.dumps({'root': {'moves': {'move': [{'id': 1}]}}}))
            (root / 'unity/fragment.json').write_text(json.dumps({'root': {'fragment': [{'id': 2}]}}))
            database = root / 'db.sqlite'
            with closing(sqlite3.connect(database)) as db:
                db.executescript('CREATE TABLE skill(id INTEGER PRIMARY KEY); INSERT INTO skill VALUES(1); CREATE TABLE factor(id INTEGER PRIMARY KEY, skill_id INTEGER REFERENCES skill(id)); INSERT INTO factor VALUES(2,999);')
            with self.assertRaisesRegex(ValueError, 'Foreign key violations: total=1'):
                validate_source_sets(database, root)

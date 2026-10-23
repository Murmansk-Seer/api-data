import json
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from scripts.verify_source_contract import validate_source_sets


class SourceContract(unittest.TestCase):
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

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from scripts.verify_source_contract import (
    validate_source_sets, validate_source_references, validate_reference_preservation,
    prepare_reference_output,
)


class SourceContract(unittest.TestCase):
    def test_reference_cleanup_preserves_other_resources_and_rejects_traversal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ('data', 'sharded_data'):
                path = root / 'v1' / kind / 'unresolved_pet_reference/old/index.json'
                path.parent.mkdir(parents=True)
                path.write_text('old evidence')
            other = root / 'v1/data/pet/4542/index.json'
            other.parent.mkdir(parents=True)
            other.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'Invalid API version'):
                prepare_reference_output(root, '../outside')
            self.assertTrue((root / 'v1/data/unresolved_pet_reference').exists())
            prepare_reference_output(root, 'v1')
            self.assertEqual(other.read_text(), 'keep')
            self.assertFalse((root / 'v1/data/unresolved_pet_reference').exists())
            self.assertFalse((root / 'v1/sharded_data/unresolved_pet_reference').exists())
            prepare_reference_output(root, 'v1')

    def source(self, root, references=False):
        (root / 'unity').mkdir()
        data = {
            'monsters.json': {'monsters': {'monster': [{'id': 4542}]}},
            'effectIcon.json': {'root': {'effect': [{'id': 1753, 'pet_id': [4543], 'tips': '', 'args': ''}] if references else []}},
            'effectDes.json': {'root': {'item': [{'id': 117, 'monster': '4543,4542'}] if references else []}},
            'moves.json': {'root': {'moves': {'move': [{'id': 29481}, {'id': 38595}]}}},
            'fragment.json': {'root': {'fragment': [{'id': 2400001}]}},
        }
        for name, content in data.items():
            (root / 'unity' / name).write_text(json.dumps(content))
        return data

    def database(self, path):
        db = sqlite3.connect(path)
        db.executescript('''
            CREATE TABLE skill(id INTEGER PRIMARY KEY);
            INSERT INTO skill VALUES(29481),(38595);
            CREATE TABLE factor(id INTEGER PRIMARY KEY, skill_id INTEGER REFERENCES skill(id));
            INSERT INTO factor(id) VALUES(2400001);
            CREATE TABLE pet(id INTEGER PRIMARY KEY);
            INSERT INTO pet VALUES(4542);
            CREATE TABLE soulmark(id INTEGER PRIMARY KEY);
            INSERT INTO soulmark VALUES(1753);
            CREATE TABLE glossary_entry(id INTEGER PRIMARY KEY);
            INSERT INTO glossary_entry VALUES(117);
            CREATE TABLE petsoulmarklink(pet_id INTEGER REFERENCES pet(id), soulmark_id INTEGER REFERENCES soulmark(id));
            CREATE TABLE petglossaryentrylink(pet_id INTEGER REFERENCES pet(id), glossary_entry_id INTEGER REFERENCES glossary_entry(id));
            CREATE TABLE unresolved_pet_reference(id INTEGER PRIMARY KEY, owner_resource TEXT, owner_id INTEGER, target_pet_id INTEGER, source_file TEXT, source_field TEXT, source_json TEXT, source_sha256 TEXT, reason TEXT);
        ''')
        db.commit()
        return db

    def preserve(self, db, root):
        _, _, missing = validate_source_references(root)
        for index, ((resource, owner, target), (filename, field, raw)) in enumerate(missing.items(), 1):
            payload = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            db.execute('INSERT INTO unresolved_pet_reference VALUES(?,?,?,?,?,?,?,?,?)', (
                index, resource, owner, target, filename, field, payload,
                hashlib.sha256(payload.encode()).hexdigest(), 'target_missing',
            ))
        db.execute('INSERT INTO petglossaryentrylink VALUES(4542,117)')
        db.commit()

    def test_real_dangling_references_are_reported_without_mutating_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.source(root, references=True)
            data['monsters.json']['monsters']['monster'].extend([{'id': 15001}, {'id': 5270}])
            (root / 'unity/monsters.json').write_text(json.dumps(data['monsters.json']))
            before = {p.name: p.read_bytes() for p in (root / 'unity').iterdir()}
            _, _, missing = validate_source_references(root)
            self.assertEqual(set(missing), {('soulmark', 1753, 4543), ('glossary_entry', 117, 4543)})
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'unity').iterdir()})
            data['monsters.json']['monsters']['monster'].insert(0, {'id': 4543})
            (root / 'unity/monsters.json').write_text(json.dumps(data['monsters.json']))
            self.assertEqual(validate_source_references(root)[2], {})

    def test_complete_ids_and_missing_row(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.source(root)
            database = root / 'db.sqlite'
            with closing(self.database(database)) as db:
                validate_source_sets(database, root)
                db.execute('DELETE FROM skill WHERE id=29481')
                db.commit()
                with self.assertRaisesRegex(ValueError, 'skill source ID mismatch'):
                    validate_source_sets(database, root)

    def test_unrelated_dangling_fk_still_blocks_publication(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.source(root)
            database = root / 'db.sqlite'
            with closing(self.database(database)) as db:
                db.execute('UPDATE factor SET skill_id=999')
                db.commit()
                with self.assertRaisesRegex(ValueError, 'Foreign key violations: total=1'):
                    validate_source_sets(database, root)

    def test_full_preservation_and_recovery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.source(root, references=True)
            database = root / 'db.sqlite'
            with closing(self.database(database)) as db:
                self.preserve(db, root)
                validate_source_sets(database, root)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertIsNone(db.execute('SELECT 1 FROM pet WHERE id=4543').fetchone())
                data['monsters.json']['monsters']['monster'].append({'id': 4543})
                (root / 'unity/monsters.json').write_text(json.dumps(data['monsters.json']))
                db.executescript('INSERT INTO pet VALUES(4543); INSERT INTO petsoulmarklink VALUES(4543,1753); INSERT INTO petglossaryentrylink VALUES(4543,117); DELETE FROM unresolved_pet_reference;')
                validate_source_sets(database, root)

    def test_loss_corruption_duplicates_and_fabrication_are_rejected(self):
        for corruption in (
            'DELETE FROM unresolved_pet_reference',
            'DELETE FROM petglossaryentrylink',
            "UPDATE unresolved_pet_reference SET source_json='{}'",
            "UPDATE unresolved_pet_reference SET source_sha256='broken'",
            "UPDATE unresolved_pet_reference SET source_file='other.json'",
            'INSERT INTO pet VALUES(4543)',
            'DELETE FROM soulmark',
            'INSERT INTO unresolved_pet_reference SELECT id+100, owner_resource, owner_id, target_pet_id, source_file, source_field, source_json, source_sha256, reason FROM unresolved_pet_reference LIMIT 1',
        ):
            with self.subTest(corruption=corruption), TemporaryDirectory() as directory:
                root = Path(directory)
                self.source(root, references=True)
                with closing(self.database(':memory:')) as db:
                    self.preserve(db, root)
                    db.execute(corruption)
                    with self.assertRaises(ValueError):
                        validate_reference_preservation(db, root)

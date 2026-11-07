from pathlib import Path
import hashlib
import json
import sqlite3
from tempfile import TemporaryDirectory, gettempdir
import unittest

from scripts.generation_metadata import FIELDS, validate_generation_metadata


class GenerationMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / 'data.sqlite'
        self.source = self.root / 'source'
        (self.source / 'unity').mkdir(parents=True)
        (self.source / 'unity/.version').write_text('20261106181039', encoding='utf-8')
        self.expected = dict(
            api_url='https://api.seerapi.com', api_version='v1',
            generator_name='solaris', generator_version='106.12.2',
            data_source='https://github.com/Murmansk-Seer/config-sources.git',
            data_version='20261106181039',
            patch_source='https://github.com/Murmansk-Seer/patch-sources.git',
            patch_version='6faee7c650436eb2106414d211abf1d244986999',
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE api_metadata (' + ','.join(key + ' TEXT' for key in FIELDS) + ')')
            connection.execute('INSERT INTO api_metadata VALUES (' + ','.join('?' for _ in FIELDS) + ')', tuple(self.expected[key] for key in FIELDS))
        for kind in ('data', 'sharded_data'):
            path = self.root / 'generated/v1' / kind / 'metadata.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.expected), encoding='utf-8')

    def tearDown(self):
        assert self.root.resolve().is_relative_to(Path(gettempdir()).resolve())
        self.temporary.cleanup()

    def validate(self, expected=None):
        return validate_generation_metadata(self.database, self.source, self.root / 'generated', 'v1', self.expected if expected is None else expected)

    def test_valid_complete_bindings_are_read_only(self):
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        self.assertEqual(self.validate()['data_version'], '20261106181039')
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)

    def test_initial_empty_source_metadata_is_rejected_without_mutation(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE api_metadata SET data_source='',data_version='',patch_source='',patch_version=''")
        before = self.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'database.*data_source'):
            self.validate()
        self.assertEqual(self.database.read_bytes(), before)

    def test_stale_or_wrong_source_in_each_json_format_is_rejected(self):
        for kind in ('data', 'sharded_data'):
            with self.subTest(format=kind):
                path = self.root / 'generated/v1' / kind / 'metadata.json'
                path.write_text(json.dumps(dict(self.expected, data_version='20261030163020')), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, kind + '.*data_version'):
                    self.validate()
                path.write_text(json.dumps(self.expected), encoding='utf-8')

    def test_two_db_rows_cannot_hide_an_old_metadata_row(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute('INSERT INTO api_metadata SELECT * FROM api_metadata')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.validate()

    def test_missing_binding_and_short_patch_revision_fail(self):
        with self.assertRaisesRegex(ValueError, 'Missing generation metadata'):
            self.validate(dict(self.expected, patch_source=''))
        with self.assertRaisesRegex(ValueError, 'full patch SHA'):
            self.validate(dict(self.expected, patch_version='6faee7c'))

    def test_wrong_api_version_or_official_version_fails(self):
        with self.assertRaisesRegex(ValueError, 'differ from frozen source'):
            self.validate(dict(self.expected, data_version='20261105230633'))
        with self.assertRaisesRegex(ValueError, 'differ from frozen source'):
            self.validate(dict(self.expected, api_version='v2'))

    def test_missing_json_metadata_fails(self):
        (self.root / 'generated/v1/sharded_data/metadata.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()

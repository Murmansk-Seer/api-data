import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('history', Path(__file__).resolve().parents[1] / 'scripts/source_history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


class SourceHistoryTests(unittest.TestCase):
    def test_noop_and_reappearance_keep_correct_generation_predecessors(self):
        initial = dict(schema_version=1, generations=[], latest_entities={})
        entities = {c: [] for c in history.CATEGORIES}
        entities['pet'] = [1, 13311]
        first, identity = history.advance(initial, entities, {'config': 'A'})
        repeated, same = history.advance(first, entities, {'config': 'A'})
        self.assertEqual(identity, same)
        self.assertIs(first, repeated)
        changed = dict(entities, pet=[1])
        second, second_id = history.advance(first, changed, {'config': 'B'})
        self.assertEqual(second['generations'][-1]['additions'], [])
        third, third_id = history.advance(second, entities, {'config': 'A'})
        self.assertNotEqual(identity, third_id)
        self.assertEqual(third['generations'][-1]['base_generation'], second_id)
        self.assertEqual(third['generations'][-1]['additions'], [dict(category='pet', entity_id=13311)])
        self.assertEqual(history.advance(third, entities, {'config': 'A'})[1], third_id)

    def test_tooling_changes_create_explicit_generation_without_fake_additions(self):
        initial = dict(schema_version=1, generations=[], latest_entities={})
        entities = {c: [] for c in history.CATEGORIES}
        first, identity = history.advance(initial, entities, {'tooling': 'old'})
        second, newer = history.advance(first, entities, {'tooling': 'new'})
        self.assertNotEqual(identity, newer)
        self.assertEqual(second['generations'][-1]['additions'], [])

    def test_same_official_version_reparse_retains_original_source_additions(self):
        entities = {c: [] for c in history.CATEGORIES}
        initial = dict(schema_version=1, generations=[], latest_entities=entities)
        current = dict(entities, pet=[13311])
        first, original = history.advance(initial, current, {'official_config_version': 'version', 'tooling': 'old'})
        second, newer = history.advance(first, current, {'official_config_version': 'version', 'tooling': 'new'})
        self.assertNotEqual(original, newer)
        self.assertEqual(first['generations'][-1]['additions'], second['generations'][-1]['additions'])
        self.assertEqual(first['generations'][-1]['base_generation'], second['generations'][-1]['base_generation'])

    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for category in history.CATEGORIES:
            self.write(category, [])

    def write(self, category, ids):
        import json
        folder = self.directory / category
        folder.mkdir(exist_ok=True)
        (folder / 'index.json').write_text(json.dumps(dict(count=len(ids), results=[dict(id=i) for i in ids], next=None, previous=None)))
        for identity in ids:
            detail = folder / str(identity)
            detail.mkdir(exist_ok=True)
            (detail / 'index.json').write_text(json.dumps(dict(id=identity)))

    def test_indexed_ids_are_sorted_and_unreferenced_old_details_are_ignored(self):
        self.write('pet', [13311, 1])
        stale = self.directory / 'pet' / '99999'
        stale.mkdir()
        (stale / 'index.json').write_text('{"id":99999}')
        self.assertEqual(history.entity_ids(self.directory)['pet'], [1, 13311])

    def test_missing_or_mismatched_detail_blocks_generation(self):
        self.write('pet', [13311])
        detail = self.directory / 'pet/13311/index.json'
        detail.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing resource detail'):
            history.entity_ids(self.directory)
        detail.write_text('{"id":1}')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            history.entity_ids(self.directory)

    def test_duplicate_boolean_zero_and_negative_ids_are_rejected(self):
        for ids in ([1, 1], [True], [0], [-1]):
            with self.subTest(ids=ids):
                self.write('pet', ids)
                with self.assertRaisesRegex(ValueError, 'Invalid or duplicate'):
                    history.entity_ids(self.directory)

    def test_partial_or_paginated_list_is_rejected(self):
        import json
        file = self.directory / 'pet/index.json'
        for document in (dict(count=1, results=[]), dict(count=0, results=[], next='page2'), dict(count=True, results=[])):
            with self.subTest(document=document):
                file.write_text(json.dumps(document))
                with self.assertRaisesRegex(ValueError, 'Incomplete resource list'):
                    history.entity_ids(self.directory)

    def test_missing_resource_list_is_rejected(self):
        (self.directory / 'skill/index.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing complete resource list'):
            history.entity_ids(self.directory)

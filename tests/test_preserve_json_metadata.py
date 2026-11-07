import importlib.util
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

spec = importlib.util.spec_from_file_location('metadata', Path(__file__).resolve().parents[1] / 'scripts/preserve_json_metadata.py')
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.previous = Path.cwd()
        os.chdir(self.directory.name)
        subprocess.run(['git', 'init', '--initial-branch=main'], check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'], check=True)
        self.path = Path('data/v1/data/metadata.json')
        self.path.parent.mkdir(parents=True)
        self.original = dict(api_version='v1', data_version='20261106181039', generate_time='before', hash='old')
        self.path.write_text(json.dumps(self.original))
        subprocess.run(['git', 'add', 'data'], check=True)
        subprocess.run(['git', 'commit', '-m', 'data(test): seed metadata'], check=True, capture_output=True)
        self.head = subprocess.check_output(['git', 'rev-parse', 'HEAD'])

    def tearDown(self):
        os.chdir(self.previous)
        self.directory.cleanup()

    def test_timestamp_only_rebuild_does_not_change_the_source_tree_or_head(self):
        self.path.write_text(json.dumps(dict(self.original, generate_time='after', hash='new')))
        self.assertEqual(metadata.preserve_metadata(), [self.path.as_posix()])
        subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', 'data'], check=True, capture_output=True)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD']), self.head)

    def test_real_version_change_is_preserved(self):
        changed = dict(self.original, data_version='new', generate_time='after', hash='new')
        self.path.write_text(json.dumps(changed))
        self.assertEqual(metadata.preserve_metadata(), [])
        self.assertEqual(json.loads(self.path.read_text()), changed)

    def test_null_zero_and_false_remain_distinct_semantic_values(self):
        self.assertNotEqual(metadata.semantic_metadata({'value': 0}), metadata.semantic_metadata({'value': False}))
        self.assertNotEqual(metadata.semantic_metadata({'value': None}), metadata.semantic_metadata({'value': ''}))

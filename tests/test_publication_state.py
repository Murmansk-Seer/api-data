import importlib.util
import os
import json
from pathlib import Path
from unittest.mock import patch
from scripts import source_history as history
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('publication_state', Path(__file__).resolve().parents[1] / 'scripts/publication_state.py')
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous = Path.cwd()
        os.chdir(self.directory.name)
        Path('.github/workflows').mkdir(parents=True)
        Path('.github/workflows/main.yml').write_text('parser: pinned')
        Path('scripts').mkdir()
        self.sources = dict(config='1' * 40, patch='2' * 40, tooling='3' * 40, official_config_version='20261106181039')
        self.document, self.generation = history.advance(dict(schema_version=1, generations=[], latest_entities={}), {c: [] for c in history.CATEGORIES}, self.sources)
        history.INDEX.parent.mkdir(parents=True)
        history.INDEX.write_text(json.dumps(self.document))
        env = patch.dict(os.environ, GENERATION_ID=self.generation, SEERAPI_TOOLING_REVISION=self.sources['tooling'])
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        os.chdir(self.previous)
        self.directory.cleanup()

    def test_only_verified_record_allows_skip_and_notification_ack(self):
        check = state.check(self.sources['config'], self.sources['patch'])
        self.assertEqual(check['skip'], 'false')
        # A failed upload never invokes record, so the next scheduled run retries.
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['skip'], 'false')
        state.record(self.sources['config'], self.sources['patch'], 'a' * 64, '4' * 40, check['fingerprint'])
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['skip'], 'true')
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['notify'], 'true')
        # Failed dispatch leaves the receipt absent and is retried without build.
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['notify'], 'true')
        state.ACK.write_text(check['fingerprint'])
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['notify'], 'false')

    def test_code_parser_and_source_changes_force_rebuild(self):
        current = state.check(self.sources['config'], self.sources['patch'])
        state.record(self.sources['config'], self.sources['patch'], 'b' * 64, '4' * 40, current['fingerprint'])
        self.assertEqual(state.check('5' * 40, self.sources['patch'])['skip'], 'false')
        Path('.github/workflows/main.yml').write_text('parser: newer')
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['skip'], 'false')

    def test_workflow_publication_precedes_state_and_receipt(self):
        workflow = (self.previous / '.github/workflows/main.yml').read_text()
        self.assertLess(workflow.index('id: verify'), workflow.index('scripts/publication_state.py record'))
        self.assertLess(workflow.index('id: dispatch'), workflow.index('scripts/publication_state.py ack'))

    def test_receipt_records_the_exact_generation_and_index_revision(self):
        current = state.check(self.sources['config'], self.sources['patch'])
        state.record(self.sources['config'], self.sources['patch'], 'a' * 64, '4' * 40, current['fingerprint'])
        receipt = state.load_state()
        self.assertEqual(receipt['generation_id'], self.generation)
        self.assertEqual(receipt['source_history_index_revision'], '4' * 40)
        self.assertEqual(receipt['tooling_revision'], self.sources['tooling'])
        self.assertEqual(receipt['official_config_version'], '20261106181039')

    def test_unknown_generation_or_source_cannot_replace_prior_receipt(self):
        state.STATE.parent.mkdir()
        before = b'{"previous":"untouched"}'
        state.STATE.write_bytes(before)
        for identity, config, revision in [('', self.sources['config'], '4' * 40), ('0' * 64, self.sources['config'], '4' * 40), (self.generation, '9' * 40, '4' * 40), (self.generation, self.sources['config'], 'main')]:
            with self.subTest(identity=identity, config=config, revision=revision), patch.dict(os.environ, GENERATION_ID=identity):
                with self.assertRaises(ValueError):
                    state.record(config, self.sources['patch'], 'a' * 64, revision, 'b' * 64)
                self.assertEqual(state.STATE.read_bytes(), before)
                self.assertFalse(Path('.build-state/config-sources-revision').exists())

    def test_same_fingerprint_without_matching_generation_requires_rebuild(self):
        current = state.check(self.sources['config'], self.sources['patch'])
        state.STATE.parent.mkdir()
        state.STATE.write_text(json.dumps(dict(fingerprint=current['fingerprint'])))
        self.assertEqual(state.check(self.sources['config'], self.sources['patch'])['skip'], 'false')

    def test_workflow_advances_verified_index_before_staging_and_receipt(self):
        text = (self.previous / '.github/workflows/main.yml').read_text()
        self.assertLess(text.index('python3 scripts/source_history.py'), text.index('git add data'))
        self.assertLess(text.index('GENERATION_ID=$generation_id'), text.index('id: verify'))
        self.assertLess(text.index('id: verify'), text.index('scripts/publication_state.py record'))


if __name__ == '__main__':
    unittest.main()

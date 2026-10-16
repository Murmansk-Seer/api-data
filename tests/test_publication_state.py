import importlib.util
import os
from pathlib import Path
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

    def tearDown(self):
        os.chdir(self.previous)
        self.directory.cleanup()

    def test_only_verified_record_allows_skip_and_notification_ack(self):
        check = state.check('config', 'patch')
        self.assertEqual(check['skip'], 'false')
        # A failed upload never invokes record, so the next scheduled run retries.
        self.assertEqual(state.check('config', 'patch')['skip'], 'false')
        state.record('config', 'patch', 'a' * 64, 'commit', check['fingerprint'])
        self.assertEqual(state.check('config', 'patch')['skip'], 'true')
        self.assertEqual(state.check('config', 'patch')['notify'], 'true')
        # Failed dispatch leaves the receipt absent and is retried without build.
        self.assertEqual(state.check('config', 'patch')['notify'], 'true')
        state.ACK.write_text(check['fingerprint'])
        self.assertEqual(state.check('config', 'patch')['notify'], 'false')

    def test_code_parser_and_source_changes_force_rebuild(self):
        current = state.check('config', 'patch')
        state.record('config', 'patch', 'b' * 64, 'commit', current['fingerprint'])
        self.assertEqual(state.check('new-config', 'patch')['skip'], 'false')
        Path('.github/workflows/main.yml').write_text('parser: newer')
        self.assertEqual(state.check('config', 'patch')['skip'], 'false')

    def test_workflow_publication_precedes_state_and_receipt(self):
        workflow = (self.previous / '.github/workflows/main.yml').read_text()
        self.assertLess(workflow.index('id: verify'), workflow.index('scripts/publication_state.py record'))
        self.assertLess(workflow.index('id: dispatch'), workflow.index('scripts/publication_state.py ack'))


if __name__ == '__main__':
    unittest.main()

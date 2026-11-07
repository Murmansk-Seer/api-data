from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.verify_source_contract import SOMUA_OUTPUT_SCOPES, prepare_reference_output


class OwnedOutputTests(unittest.TestCase):
    def test_disabled_tables_remove_stale_details_and_names_without_touching_other_resources(self):
        self.assertEqual(len(SOMUA_OUTPUT_SCOPES), 27)
        self.assertEqual(len(set(SOMUA_OUTPUT_SCOPES)), 27)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ('data', 'sharded_data'):
                for resource in SOMUA_OUTPUT_SCOPES:
                    path = root / 'v1' / kind / resource / 'old-name/index.json'
                    path.parent.mkdir(parents=True)
                    path.write_text('stale')
            retained = root / 'v1/data/pet/13311/index.json'
            retained.parent.mkdir(parents=True)
            retained.write_text('retain SP')
            prepare_reference_output(root, 'v1')
            self.assertEqual(retained.read_text(), 'retain SP')
            for kind in ('data', 'sharded_data'):
                for resource in SOMUA_OUTPUT_SCOPES:
                    self.assertFalse((root / 'v1' / kind / resource).exists())

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.publication_state import fingerprint


class SomuaPipelineTests(unittest.TestCase):
    def test_revision_changes_build_fingerprint_without_config_change(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                Path(".github/workflows").mkdir(parents=True)
                Path(".github/workflows/main.yml").write_text("same workflow")
                with patch.dict(os.environ, {"SEERAPI_TOOLING_REVISION": "a" * 40}):
                    first = fingerprint("config", "patch")
                with patch.dict(os.environ, {"SEERAPI_TOOLING_REVISION": "b" * 40}):
                    self.assertNotEqual(first, fingerprint("config", "patch"))
            finally:
                os.chdir(previous)

    def test_same_revision_and_frozen_source_are_required_before_analysis(self):
        text = (Path(__file__).parents[1] / ".github/workflows/main.yml").read_text("utf-8")
        self.assertRegex(text, r'SEERAPI_TOOLING_REVISION: [0-9a-f]{40}')
        self.assertIn('@${SEERAPI_TOOLING_REVISION}#subdirectory=packages/seerapi-models', text)
        self.assertIn('@${SEERAPI_TOOLING_REVISION}#subdirectory=packages/solaris', text)
        self.assertLess(text.index('cat source/unity/.parser-revision'), text.index('solaris analyze data'))
        self.assertIn('cat source/unity/.somua-version', text)

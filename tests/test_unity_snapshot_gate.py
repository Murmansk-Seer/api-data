from pathlib import Path
import tempfile
import unittest

from scripts.verify_unity_snapshot import verify_unity_snapshot


class SnapshotGateTests(unittest.TestCase):
    def test_matching_complete_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in {
                ".version": "20261113190033",
                ".somua-version": "20261113190033",
                ".parser-revision": "a" * 40,
            }.items():
                (root / name).write_text(value)
            self.assertEqual(verify_unity_snapshot(root, "a" * 40), "20261113190033")

    def test_mismatch_reports_file_actual_expected_and_never_changes_source(self):
        for name, value in (
            (".version", "broken"),
            (".somua-version", "20261111114936"),
            (".parser-revision", "b" * 40),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for marker, data in {
                    ".version": "20261113190033",
                    ".somua-version": "20261113190033",
                    ".parser-revision": "a" * 40,
                }.items():
                    (root / marker).write_text(value if marker == name else data)
                before = {p.name: p.read_bytes() for p in root.iterdir()}
                with self.assertRaisesRegex(ValueError, rf"{name}.*actual=.*expected="):
                    verify_unity_snapshot(root, "a" * 40)
                self.assertEqual(
                    before, {p.name: p.read_bytes() for p in root.iterdir()}
                )

    def test_missing_marker_preserves_exception_and_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "actual=unreadable") as caught:
                verify_unity_snapshot(Path(directory), "a" * 40)
            self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)

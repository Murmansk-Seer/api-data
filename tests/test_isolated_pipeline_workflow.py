from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IsolatedWorkflowTests(unittest.TestCase):
    def test_migration_is_required_before_restore_tests_or_generation(self):
        text = (ROOT / '.github/workflows/main.yml').read_text()
        gate = text.index('name: Require migrated pipeline checkpoint')
        restore = text.index('name: Restore verified pipeline checkpoint')
        self.assertLess(gate, restore)
        self.assertLess(restore, text.index('name: Publication and network regression tests'))
        self.assertLess(restore, text.index('name: Check data source changes'))
        self.assertIn('git ls-remote --exit-code --heads origin refs/heads/pipeline-state', text)

    def test_verified_state_and_confirmed_ack_do_not_commit_to_main(self):
        text = (ROOT / '.github/workflows/main.yml').read_text()
        self.assertNotIn('git add .build-state', text)
        self.assertNotIn('Record verified api-data publication', text)
        self.assertNotIn('Record SeerAPI notification receipt', text)
        publication = text.index('name: Persist verified publication checkpoint')
        notification = text.index('name: Persist confirmed notification checkpoint')
        self.assertLess(text.index('scripts/publication_state.py record'), publication)
        self.assertLess(publication, text.index('name: Trigger SeerAPI build'))
        self.assertLess(text.index('scripts/publication_state.py ack'), notification)
        for name, guard in [('Persist verified publication checkpoint', "steps.verify.outcome == 'success'"), ('Persist confirmed notification checkpoint', "steps.dispatch.outcome == 'success'")]:
            block = text.split('name: ' + name, 1)[1].split('            - name:', 1)[0]
            self.assertIn('if: ' + guard, block)
            self.assertIn('mode: publish', block)

    def test_all_state_actions_pin_the_verified_implementation(self):
        text = (ROOT / '.github/workflows/main.yml').read_text()
        refs = [line.strip().split('@', 1)[1] for line in text.splitlines() if 'uses: Murmansk-Seer/.github/.github/actions/pipeline-state@' in line]
        self.assertEqual(refs, ['e50f91b8dc44002ce0e15cad50e88f2bd34d6210'] * 3)

    def test_runtime_files_are_ignored_and_removed_from_source_index(self):
        self.assertIn('/.build-state/', (ROOT / '.gitignore').read_text())
        result = subprocess.check_output(['git', 'ls-files', '--', '.build-state'], cwd=ROOT)
        self.assertEqual(result, b'')

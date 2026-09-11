import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("push_build", Path(__file__).parents[1] / "scripts/push_build.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PushTests(unittest.TestCase):
    def exercise(self, ancestor=True, changed=False, failures=0):
        calls = []
        def fake(*args, check=True):
            calls.append(args)
            code = 0
            if args[0] == "merge-base":
                code = int(not ancestor)
            if args[0] == "diff":
                code = int(changed)
            if args[0] == "push":
                code = int(sum(c[0] == "push" for c in calls) <= failures)
            return subprocess.CompletedProcess(args, code, "remote\n", "rejected" if code else "")
        return calls, patch.object(module, "git", side_effect=fake)

    def test_normal_push(self):
        calls, mock = self.exercise()
        with mock:
            module.publish("base", "main")
        self.assertIn(("push", "origin", "HEAD:refs/heads/main"), calls)
        self.assertFalse(any(c[0] == "merge" for c in calls))

    def test_history_only_advance(self):
        calls, mock = self.exercise(ancestor=False)
        with mock:
            module.publish("base", "main")
        self.assertIn(("merge", "--no-edit", "remote"), calls)

    def test_actual_remote_change_stops_before_push(self):
        calls, mock = self.exercise(ancestor=False, changed=True)
        with mock, self.assertRaisesRegex(RuntimeError, "Remote content changed"):
            module.publish("base", "main")
        self.assertFalse(any(c[0] in {"merge", "push"} for c in calls))

    def test_push_race_rechecks(self):
        calls, mock = self.exercise(failures=1)
        with mock:
            module.publish("base", "main")
        self.assertEqual(sum(c[0] == "fetch" for c in calls), 2)

    def test_permission_failure_is_bounded(self):
        calls, mock = self.exercise(failures=10)
        with mock, self.assertRaisesRegex(RuntimeError, "bounded retries"):
            module.publish("base", "main")
        self.assertEqual(sum(c[0] == "push" for c in calls), 3)

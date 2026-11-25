"""Exercise ingress path migration with stubbed user-service commands."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


class IngressPathTests(unittest.TestCase):
    def run_launcher(self, mode):
        launcher = Path(__file__).resolve().parents[1] / "scripts/start-ingress.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "renamed lab"
            (root / "scripts").mkdir(parents=True)
            (root / "bin").mkdir()
            shutil.copy2(launcher, root / "scripts/start-ingress.sh")
            (root / "scripts/env.sh").write_text(
                f"LAB2_ROOT={shlex.quote(str(root))}\n"
                f"export PATH={shlex.quote(str(root / 'bin'))}:\"$PATH\"\n")
            stub = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ['TEST_LOG'], 'a') as stream:
    stream.write(json.dumps([Path(sys.argv[0]).name] + sys.argv[1:]) + '\\n')
if Path(sys.argv[0]).name == 'systemctl':
    if 'show' in sys.argv:
        if os.environ['TEST_MODE'] == 'matching':
            print('/usr/bin/bash ' + os.environ['TEST_ROOT'] + '/scripts/port-forward.sh')
        else:
            print('/usr/bin/bash /old/lab/scripts/port-forward.sh')
    elif 'is-active' in sys.argv:
        sys.exit(3 if os.environ['TEST_MODE'] == 'restarting' else 0)
'''
            for name in ("systemctl", "systemd-run"):
                path = root / "bin" / name
                path.write_text(stub)
                path.chmod(0o755)
            log = root / "commands.jsonl"
            environment = dict(os.environ, TEST_LOG=str(log), TEST_ROOT=str(root), TEST_MODE=mode)
            subprocess.run(["bash", str(root / "scripts/start-ingress.sh")], env=environment,
                           text=True, capture_output=True, check=True)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return calls, str(root / "scripts/port-forward.sh")

    def test_matching_active_service_is_preserved(self):
        calls, _ = self.run_launcher("matching")
        self.assertFalse(any(call[0] == "systemd-run" or "stop" in call for call in calls))

    def test_old_path_is_stopped_and_replaced(self):
        calls, path = self.run_launcher("old")
        stop = next(i for i, call in enumerate(calls) if call[0] == "systemctl" and "stop" in call)
        start = next(i for i, call in enumerate(calls) if call[0] == "systemd-run")
        self.assertLess(stop, start)
        self.assertEqual(calls[start][-1], path)

    def test_auto_restarting_old_service_is_replaced(self):
        calls, path = self.run_launcher("restarting")
        self.assertTrue(any(call[0] == "systemctl" and "stop" in call for call in calls))
        self.assertEqual(next(call for call in calls if call[0] == "systemd-run")[-1], path)


if __name__ == "__main__":
    unittest.main()

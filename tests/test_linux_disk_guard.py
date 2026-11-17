import importlib.util
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('kestrel_disk_guard', ROOT / 'linux/disk_guard.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


@unittest.skipIf(os.name == 'nt', 'Linux build process groups')
class LinuxDiskGuardTests(unittest.TestCase):
    def test_refuses_to_start_without_backing_space(self):
        with tempfile.TemporaryDirectory() as directory:
            free = shutil.disk_usage(directory).free
            self.assertEqual(guard.guarded([], directory, 1, free + 1, check_only=True), 2)

    def test_successful_child_preserves_exit_status(self):
        self.assertEqual(guard.guarded([sys.executable, '-c', 'raise SystemExit(7)'],
                                       ROOT, 1, 1), 7)

    def test_stops_its_child_when_space_threshold_is_crossed(self):
        with tempfile.TemporaryDirectory() as directory:
            free = shutil.disk_usage(directory).free
            self.assertEqual(guard.guarded([sys.executable, '-c', 'import time; time.sleep(30)'],
                                           directory, free + 1024**3, 1), 3)

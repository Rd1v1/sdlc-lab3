"""Run LAB 3 tests using the standard library; keep temporary files local."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.chdir(ROOT)
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch)
    for key in ('TMP', 'TEMP', 'TMPDIR'):
        os.environ[key] = str(scratch)
    suite = unittest.TestLoader().discover(str(ROOT / 'lab3/tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

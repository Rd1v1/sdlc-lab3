"""Shared local/CI unittest runner with a dependency-free JUnit report."""
import argparse
import compileall
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class JUnitResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def startTest(self, test):
        super().startTest(test)
        self.started = time.perf_counter()
        self.case = ET.Element('testcase', name=test.id(), classname=type(test).__name__)

    def stopTest(self, test):
        self.case.set('time', str(time.perf_counter() - self.started))
        self.cases.append(self.case)
        super().stopTest(test)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        ET.SubElement(self.case, 'failure').text = self._exc_info_to_string(err, test)

    def addError(self, test, err):
        super().addError(test, err)
        ET.SubElement(self.case, 'error').text = self._exc_info_to_string(err, test)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        ET.SubElement(self.case, 'skipped', message=reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            tag = 'failure' if issubclass(err[0], test.failureException) else 'error'
            ET.SubElement(self.case, tag, message=str(subtest)).text = self._exc_info_to_string(err, test)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--lab', choices=['1', '3', '4', '5', 'web', 'all'], default='all')
    parser.add_argument('--junit', type=Path, default=Path('artifacts/junit.xml'))
    parser.add_argument('--failure-probe', action='store_true', help='Deliberate failure to verify CI exit code')
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch)
    for key in ('TMP', 'TEMP', 'TMPDIR'):
        os.environ[key] = str(scratch)
    for source in ('lab1/src', 'lab3/src', 'lab4', 'lab5', 'lab6', 'lab7', 'lab8', 'scripts'):
        if (ROOT / source).exists() and not compileall.compile_dir(ROOT / source, quiet=1):
            return 1
    suite = unittest.TestSuite()
    available = [n for n in ('1','3','4','5') if (ROOT / f'lab{n}/tests').is_dir()]
    labs = available if args.lab == 'all' else ([n for n in ('4','5') if n in available] if args.lab == 'web' else [args.lab])
    if not labs or any(n not in available for n in labs):
        parser.error('Selected laboratory tests are absent in this repository')
    for lab in labs:
        suite.addTests(unittest.TestLoader().discover(str(ROOT / f'lab{lab}/tests')))
    if args.failure_probe:
        class DeliberateFailure(unittest.TestCase):
            def runTest(self):
                self.fail('Intentional CI failure probe')
        suite.addTest(DeliberateFailure())
    result = unittest.TextTestRunner(verbosity=2, resultclass=JUnitResult).run(suite)
    report = ET.Element('testsuite', tests=str(result.testsRun), failures=str(len(result.failures)),
                        errors=str(len(result.errors)), skipped=str(len(result.skipped)))
    report.extend(result.cases)
    args.junit.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(report).write(args.junit, encoding='utf-8', xml_declaration=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

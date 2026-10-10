import contextlib
import hashlib
import io
import threading
import unittest
from unittest.mock import patch
from lab3.src.bruteforce import CrackConfig, HashTarget, TargetError, candidate_at, crack, run


class RegressionTests(unittest.TestCase):
    def test_full_partition_no_duplicates_or_gaps(self):
        seen = []
        lock = threading.Lock()
        def absent(target, candidate):
            with lock:
                seen.append(candidate)
            return False
        config = CrackConfig('abc', 1, 3, workers=2)
        with patch.object(HashTarget, 'matches', absent):
            result = crack(HashTarget('md5', '0' * 32), config)
        self.assertEqual(result.candidates_checked, 39)
        self.assertEqual(len(set(seen)), 39)
        self.assertEqual(len(seen), 39)
        self.assertFalse(result.found)

    def test_bad_argon2_and_unsupported_algorithm(self):
        for encoded in ('$argon2id$v=19$m=8,t=1,p=8$c2FsdHNhbHQ$YWJjZA', '$argon2id$v=19$m=8192,t=1,p=1$salt$hash', '$argon2id$v=19$m=8192,t=1,p=1$!$!'):
            with self.assertRaises(TargetError):
                HashTarget.parse(encoded)
        with self.assertRaises(TargetError):
            HashTarget('unknown', 'test').matches('test')

    def test_candidate_boundary_and_wrong_match(self):
        self.assertEqual(candidate_at(0, 'ab', 2), 'aa')
        self.assertEqual(candidate_at(3, 'ab', 2), 'bb')
        for index in (-1, 4):
            with self.assertRaises(ValueError):
                candidate_at(index, 'ab', 2)
        self.assertFalse(HashTarget.parse(hashlib.md5(b'abc', usedforsecurity=False).hexdigest()).matches('abd'))

    def test_cli_status_and_cancellation(self):
        target = hashlib.md5(b'c', usedforsecurity=False).hexdigest()
        args = [target, '--alphabet', 'ab', '--max-length', '1']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run(args), 1)
            self.assertEqual(run(['invalid']), 2)
            with patch('lab3.src.cli.crack', side_effect=KeyboardInterrupt):
                self.assertEqual(run(args), 130)


if __name__ == '__main__':
    unittest.main()

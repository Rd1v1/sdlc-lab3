import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from lab3.src.models import CrackConfig
from lab3.src.hashes import HashTarget, TargetError
from lab3.src.cpu import crack
from lab3.src.wordlist import crack_wordlist, inspect_wordlist
from lab3.src.candidates import iter_candidates
from lab3.src.cli import run


class DictionaryTests(unittest.TestCase):
    def test_mask_prefix_in_both_backends(self):
        target = HashTarget.parse(hashlib.md5(b'123456', usedforsecurity=False).hexdigest())
        for backend in ('threads', 'processes'):
            config = CrackConfig('0123456789', 1, 1, workers=1, backend=backend, prefix='12345')
            self.assertEqual(list(iter_candidates(config)), ['12345'+str(i) for i in range(10)])
            result = crack(target, config)
            self.assertEqual(result.password, '123456')
            self.assertEqual(result.candidates_checked, 7)

    def test_wordlist_preserves_bytes_crlf_last_line_and_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'one\r\n\n\xffpass\nlast')
            info = inspect_wordlist(path)
            self.assertEqual(info['lines'], 4)
            target = HashTarget.parse(hashlib.md5(b'\xffpass', usedforsecurity=False).hexdigest())
            snapshots = []
            result = crack_wordlist(target, path, snapshots.append)
            self.assertTrue(result.found)
            self.assertEqual(result.password_hex, b'\xffpass'.hex())
            self.assertEqual(result.candidates_checked, 3)
            self.assertEqual(snapshots[-1][0].status, 'found')
            target = HashTarget.parse(hashlib.sha1(b'last', usedforsecurity=False).hexdigest())
            self.assertEqual(crack_wordlist(target, path).candidates_checked, 4)

    def test_empty_and_exhausted_wordlists(self):
        target = HashTarget.parse(hashlib.md5(b'absent', usedforsecurity=False).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'')
            result = crack_wordlist(target, path)
            self.assertFalse(result.found)
            self.assertEqual(result.total_candidates, 0)
            path.write_bytes(b'a\nb\n')
            result = crack_wordlist(target, path)
            self.assertFalse(result.found)
            self.assertEqual(result.candidates_checked, 2)

    def test_dictionary_all_hashes(self):
        import bcrypt
        from argon2 import PasswordHasher
        targets = [hashlib.md5(b'ba', usedforsecurity=False).hexdigest(),
                   hashlib.sha1(b'ba', usedforsecurity=False).hexdigest(),
                   bcrypt.hashpw(b'ba', bcrypt.gensalt(rounds=4)).decode(),
                   PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash('ba')]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'ab\nba\nbb\n')
            for encoded in targets:
                with self.subTest(encoded=encoded):
                    result = crack_wordlist(HashTarget.parse(encoded), path)
                    self.assertEqual(result.password, 'ba')
                    self.assertEqual(result.candidates_checked, 2)

    def test_dictionary_cli_and_worker_restriction(self):
        target = hashlib.md5(b'ba', usedforsecurity=False).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_text('ab\nba\n', encoding='utf-8')
            args = [target, '--wordlist', str(path), '--no-progress']
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(run(args), 0)
                self.assertEqual(run(args+['--workers', '2']), 2)
                self.assertEqual(run(args+['--backend', 'processes']), 2)
                self.assertEqual(run(args+['--prefix', 'bad']), 2)

    def test_dictionary_worker_error_propagates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'a\nb\n')
            with patch.object(HashTarget, 'matches', side_effect=RuntimeError('failed verifier')):
                with self.assertRaisesRegex(RuntimeError, 'failed verifier'):
                    crack_wordlist(HashTarget('md5', '0'*32), path)
            with self.assertRaises(TargetError):
                crack_wordlist(HashTarget('sha1', '0'*32), path)

    def test_dictionary_cancellation_cleans_worker(self):
        before = {thread.ident for thread in threading.enumerate()}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'a\nb\n')
            with patch.object(HashTarget, 'matches', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    crack_wordlist(HashTarget('md5', '0'*32), path)
        self.assertEqual({thread.ident for thread in threading.enumerate()}, before)


if __name__ == '__main__':
    unittest.main()

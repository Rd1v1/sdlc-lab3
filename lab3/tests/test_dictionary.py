import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from lab3.src.candidates import iter_candidates
from lab3.src.cpu import crack
from lab3.src.hashes import HashTarget
from lab3.src.models import CrackConfig


class DictionaryTests(unittest.TestCase):
    def test_binary_lines_crlf_empty_and_no_trailing_newline(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'one\r\n\n\xffpass\nlast')
            self.assertEqual(list(iter_candidates(CrackConfig(), path)), [b'one', b'', b'\xffpass', b'last'])
            for workers in (1, 2):
                target = HashTarget.parse(hashlib.md5(b'\xffpass', usedforsecurity=False).hexdigest())
                result = crack(target, CrackConfig(workers=workers), path)
                self.assertEqual(result.password_hex, b'\xffpass'.hex())
                self.assertIsNone(result.total_candidates)

    def test_empty_and_exhausted_dictionary(self):
        target = HashTarget('md5', '0'*32)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            for raw, count in ((b'', 0), (b'a\nb\n', 2)):
                path.write_bytes(raw)
                snapshots = []
                result = crack(target, CrackConfig(workers=2), path, snapshots.append)
                self.assertFalse(result.found)
                self.assertEqual(result.candidates_checked, count)
                self.assertTrue(all(row.status == 'done' for row in snapshots[-1]))

    def test_first_match_stops_without_full_file_read_or_checksum(self):
        target = HashTarget.parse(hashlib.sha1(b'first').hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'first\n'+b'other\n'*10000)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('must stream')):
                result = crack(target, CrackConfig(), path)
            self.assertEqual(result.candidates_checked, 1)
            self.assertEqual(result.password, 'first')

    def test_cancel_closes_wordlist_and_cleans_workers(self):
        before = {thread.ident for thread in threading.enumerate()}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'a\nb\n')
            with patch.object(HashTarget, 'matches', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                crack(HashTarget('md5', '0'*32), CrackConfig(workers=2), path)
            path.unlink()
        self.assertEqual({thread.ident for thread in threading.enumerate()}, before)

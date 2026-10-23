import contextlib
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab3.src.models import CrackConfig
from lab3.src.hashes import HashTarget
from lab3.src.cli import run


@unittest.skipUnless(os.environ.get('LAB3_GPU_TESTS') == '1', 'Set LAB3_GPU_TESTS=1 to execute real GPU tests')
class GpuTests(unittest.TestCase):
    def test_all_assignment_hashes_with_control_wordlist(self):
        import json
        from lab3.src.gpu import search_gpu
        data = json.loads((Path(__file__).parents[1]/'examples/assignment-hashes.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'123456\napple\n')
            for algorithm in ('md5', 'sha1', 'bcrypt', 'argon2id'):
                for level, encoded in data[algorithm].items():
                    with self.subTest(algorithm=algorithm, level=level):
                        result = search_gpu(HashTarget.parse(encoded), CrackConfig('ab', 1, 1), path, batch_size=2)
                        expected = {'easy': '123456', 'medium': 'apple'}.get(level)
                        self.assertEqual(result['password'], expected)
                        self.assertEqual(result['found'], expected is not None)
                        self.assertEqual(result['candidates_checked'], 2)

    def test_md5_sha1_full_digests_and_block_boundaries(self):
        from lab3.src.gpu import GpuHasher
        candidates = [b'', b'a', b'abc', b'x'*55, b'x'*56, b'x'*63, b'x'*64, b'x'*65, b'x'*256, 'пароль'.encode()]
        for algorithm in ('md5', 'sha1'):
            target = HashTarget.parse(hashlib.new(algorithm, b'abc', usedforsecurity=False).hexdigest())
            engine = GpuHasher(target)
            output = engine.digest_batch(candidates)
            self.assertEqual(output, [hashlib.new(algorithm, candidate, usedforsecurity=False).digest() for candidate in candidates])
            self.assertEqual(engine.device_info()['type'], 'GPU')
            self.assertGreater(engine.kernel_seconds, 0)

    def test_bcrypt_all_digest_bytes_and_password_lengths(self):
        import bcrypt
        from lab3.src.gpu import GpuHasher, _bcrypt_decode
        candidates = [b'', b'abc', b'abd', b'x'*72, 'пароль'.encode()]
        salt = bcrypt.gensalt(rounds=4)
        target = HashTarget.parse(bcrypt.hashpw(b'abc', salt).decode())
        engine = GpuHasher(target)
        self.assertEqual(engine.digest_batch(candidates), [_bcrypt_decode(bcrypt.hashpw(candidate, salt).decode()[29:]) for candidate in candidates])
        self.assertGreater(engine.kernel_seconds, 0)

    def test_argon2_gpu_memory_passes_and_lanes(self):
        from argon2.low_level import Type, hash_secret
        from lab3.src.gpu import GpuHasher
        import base64
        for memory, iterations, lanes in ((8192, 1, 1), (65536, 3, 2)):
            candidates = [b'123456', b'123457']
            encoded = [hash_secret(candidate, b'saltsalt', iterations, memory, lanes, 32, Type.ID).decode() for candidate in candidates]
            engine = GpuHasher(HashTarget.parse(encoded[0]))
            self.assertEqual(engine.digest_batch(candidates), [base64.b64decode(value.split('$')[-1]+'=') for value in encoded])
            self.assertGreater(engine.kernel_seconds, 0)

    def test_gpu_search_and_wordlist_do_not_call_hashcat(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'123456', usedforsecurity=False).hexdigest())
        with patch('subprocess.run', side_effect=AssertionError('Own GPU backend must not invoke hashcat')):
            result = search_gpu(target, CrackConfig('0123456789', 1, 1, prefix='12345'))
            self.assertEqual(result['password'], '123456')
            self.assertEqual(result['backend'], 'gpu')
            self.assertEqual(result['candidates_checked'], 10)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'words.txt'
                path.write_bytes(b'other\n123456\n')
                result = search_gpu(target, CrackConfig('a', 1, 1), path, batch_size=2)
                self.assertEqual(result['password'], '123456')
                self.assertEqual(result['candidates_checked'], 2)

    def test_binary_wordlist_and_rejected_lengths(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'\xffpass', usedforsecurity=False).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'x'*257+b'\n\xffpass\n')
            result = search_gpu(target, CrackConfig('a', 1, 1), path, batch_size=2)
            self.assertTrue(result['found'])
            self.assertEqual(result['rejected'], 1)
            self.assertEqual(result['password_hex'], b'\xffpass'.hex())

    def test_exhausted_search(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.sha1(b'absent', usedforsecurity=False).hexdigest())
        result = search_gpu(target, CrackConfig('ab', 1, 2), batch_size=3)
        self.assertFalse(result['found'])
        self.assertEqual(result['candidates_checked'], 6)

    def test_gpu_worker_progress_counts_and_verified_results(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'cc', usedforsecurity=False).hexdigest())
        snapshots = []
        result = search_gpu(target, CrackConfig('abc', 1, 2), batch_size=2, on_progress=snapshots.append)
        self.assertEqual(result['password'], 'cc')
        self.assertEqual(result['workers'], 2)
        self.assertTrue(all([row.worker for row in rows] == [1, 2] for rows in snapshots))
        self.assertEqual([row.checked for row in snapshots[-1]], [6, 6])
        self.assertEqual([row.found_password for row in snapshots[-1]], [None, 'cc'])
        self.assertEqual([row.status for row in snapshots[-1]], ['done', 'found'])
        for worker in range(2):
            counts = [rows[worker].checked for rows in snapshots]
            self.assertEqual(counts, sorted(counts))

    def test_gpu_duplicate_matches_and_idle_worker_in_short_last_batch(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'a', usedforsecurity=False).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'a\na\n')
            snapshots = []
            search_gpu(target, CrackConfig('ab', 1, 1), path, batch_size=2, on_progress=snapshots.append)
            self.assertEqual([row.found_password for row in snapshots[-1]], ['a', 'a'])
            path.write_bytes(b'b\nc\nd\n')
            snapshots = []
            result = search_gpu(target, CrackConfig('ab', 1, 1), path, batch_size=2, on_progress=snapshots.append)
            self.assertFalse(result['found'])
            self.assertEqual([row.checked for row in snapshots[-1]], [2, 1])
            self.assertEqual([row.candidate for row in snapshots[-1]], ['d', 'c'])
            self.assertTrue(all(row.status == 'done' and row.found_password is None for row in snapshots[-1]))

    def test_limits_and_no_cpu_fallback(self):
        from argon2 import PasswordHasher
        from lab3.src.gpu import GpuHasher, search_gpu
        target = HashTarget.parse(hashlib.md5(b'abc', usedforsecurity=False).hexdigest())
        with self.assertRaises(RuntimeError):
            GpuHasher(target, device_index=999)
        with self.assertRaises(ValueError):
            GpuHasher(HashTarget('sha1', target.encoded))
        with self.assertRaises(ValueError):
            GpuHasher(target).digest_batch([b'x'*257])
        argon = HashTarget.parse(PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash('a'))
        with self.assertRaises(ValueError):
            search_gpu(argon, CrackConfig('a', 1, 1), batch_size=33)

    def test_gpu_cli_and_invalid_device(self):
        target = hashlib.md5(b'c', usedforsecurity=False).hexdigest()
        args = [target, '--backend', 'gpu', '--alphabet', 'abc', '--max-length', '1', '--no-progress']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run(args), 0)
            self.assertEqual(run(args+['--gpu-device', '999']), 2)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(run(args[:-1]+['--workers', '3', '--progress']), 0)
        import json
        self.assertEqual(json.loads(stdout.getvalue())['workers'], 3)
        self.assertIn('FOUND by worker 3: "c"', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()

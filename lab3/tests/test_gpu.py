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
    def test_32_workers_with_scrollable_terminal(self):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from lab3.src.gpu import search_gpu
        from lab3.src.progress import CliProgress
        from lab3.src.terminal import WorkerTerminal
        config = CrackConfig('0123456789', 3, 3, 32, True)
        target = HashTarget.parse(hashlib.md5(b'999', usedforsecurity=False).hexdigest())
        progress = CliProgress(config, stream=io.StringIO(), total_candidates=1000)
        with create_pipe_input() as source:
            terminal = WorkerTerminal(progress, lambda callback: search_gpu(target, config, on_progress=callback),
                                      input=source, output=DummyOutput())
            result = terminal.run()
        self.assertEqual(result.password, '999')
        self.assertEqual(result.candidates_checked, 1000)
        self.assertEqual(terminal.table.document.line_count, 32)
        self.assertEqual(progress.rows[7].found_password, '999')
        self.assertEqual(sum(row.checked for row in progress.rows), 1000)
        self.assertFalse(terminal.worker.is_alive())

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
                        result = search_gpu(HashTarget.parse(encoded), CrackConfig('ab', 1, 1, 2, True), path)
                        expected = {'easy': '123456', 'medium': 'apple'}.get(level)
                        self.assertEqual(result.password, expected)
                        self.assertEqual(result.found, expected is not None)
                        self.assertEqual(result.candidates_checked, 2)

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

    def test_gpu_search_does_not_invoke_hashcat(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'cc', usedforsecurity=False).hexdigest())
        with patch('subprocess.run', side_effect=AssertionError('must not invoke hashcat')):
            result = search_gpu(target, CrackConfig('abc', 2, 2, 4, True))
        self.assertEqual(result.password, 'cc')
        self.assertEqual(result.candidates_checked, 9)
        self.assertGreater(result.gpu_kernel_seconds, 0)

    def test_worker_counts_matches_duplicates_and_short_last_batch(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'a', usedforsecurity=False).hexdigest())
        config = CrackConfig(workers=2, gpu=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            for content, expected_counts, expected_passwords in (
                    (b'a\na\n', [1, 1], ['a', 'a']), (b'b\nc\nd\n', [2, 1], [None, None])):
                path.write_bytes(content)
                snapshots = []
                result = search_gpu(target, config, path, snapshots.append)
                self.assertEqual([row.checked for row in snapshots[-1]], expected_counts)
                self.assertEqual([row.found_password for row in snapshots[-1]], expected_passwords)
                self.assertEqual(sum(row.checked for row in snapshots[-1]), result.candidates_checked)
                self.assertTrue(all([row.worker for row in rows] == [1, 2] for rows in snapshots))

    def test_binary_dictionary_and_rejected_lengths(self):
        from lab3.src.gpu import search_gpu
        target = HashTarget.parse(hashlib.md5(b'\xffpass', usedforsecurity=False).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'words.txt'
            path.write_bytes(b'x'*257+b'\n\xffpass\n')
            rows = []
            result = search_gpu(target, CrackConfig(workers=2, gpu=True), path, rows.append)
            self.assertEqual(result.rejected, 1)
            self.assertEqual(result.password_hex, b'\xffpass'.hex())
            self.assertEqual([row.status for row in rows[-1]], ['skipped', 'found'])

    def test_exhaustion(self):
        from lab3.src.gpu import search_gpu
        result = search_gpu(HashTarget('md5', '0'*32), CrackConfig('ab', 1, 2, 3, True))
        self.assertFalse(result.found)
        self.assertEqual(result.candidates_checked, 6)

    def test_limits_and_gpu_missing_without_cpu_fallback(self):
        import pyopencl as cl
        from argon2 import PasswordHasher
        from lab3.src.gpu import GpuHasher, search_gpu
        target = HashTarget.parse(hashlib.md5(b'abc', usedforsecurity=False).hexdigest())
        with patch.object(cl, 'get_platforms', return_value=[]), self.assertRaises(RuntimeError):
            GpuHasher(target)
        for failing_api in ('Context', 'Program'):
            with patch.object(cl, failing_api, side_effect=cl.RuntimeError('unavailable')):
                with self.subTest(api=failing_api), self.assertRaisesRegex(RuntimeError, 'OpenCL'):
                    GpuHasher(target)
        with self.assertRaises(ValueError):
            GpuHasher(HashTarget('sha1', target.encoded))
        with self.assertRaises(ValueError):
            GpuHasher(target).digest_batch([b'x'*257])
        argon = HashTarget.parse(PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash('a'))
        with self.assertRaises(ValueError):
            search_gpu(argon, CrackConfig('a', 1, 1, 33, True))

    def test_gpu_cli_and_password_per_worker(self):
        import json
        args = [hashlib.md5(b'c', usedforsecurity=False).hexdigest(), '--gpu', '--workers', '3',
                '--alphabet', 'abc', '--max-length', '1']
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(run(args), 0)
        self.assertEqual(json.loads(stdout.getvalue())['password'], 'c')
        self.assertIn('FOUND by worker 3: "c"', stderr.getvalue())
        with patch('lab3.src.gpu.GpuHasher', side_effect=RuntimeError('no GPU')):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(run(args), 2)

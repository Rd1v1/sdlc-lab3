import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from lab3.src.cli import run
from lab3.src.cpu import crack
from lab3.src.hashes import HashTarget
from lab3.src.models import CrackConfig, WorkerProgress
from lab3.src.progress import CliProgress


class WorkerTests(unittest.TestCase):
    def test_one_worker_runs_on_main_thread_without_executor(self):
        caller = threading.get_ident()
        threads = []
        with patch('lab3.src.cpu.ThreadPoolExecutor', side_effect=AssertionError('single worker must be sequential')):
            with patch.object(HashTarget, 'matches', side_effect=lambda raw: threads.append(threading.get_ident()) or False):
                crack(HashTarget('md5', '0'*32), CrackConfig('ab', 1, 2))
        self.assertEqual(threads, [caller]*6)

    def test_shared_stream_has_no_gaps_duplicates_and_live_progress(self):
        seen, snapshots = [], []
        def check(target, raw):
            seen.append(raw)
            time.sleep(0.008)
            return False
        with patch.object(HashTarget, 'matches', check):
            result = crack(HashTarget('md5', '0'*32), CrackConfig('abc', 1, 3, 2), on_progress=snapshots.append)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), 39)
        self.assertEqual(sum(row.checked for row in snapshots[-1]), result.candidates_checked)
        self.assertTrue(all(row.checked > 0 and row.status == 'done' for row in snapshots[-1]))
        self.assertTrue(any(row.status == 'running' for rows in snapshots for row in rows))
        for worker in range(2):
            counts = [rows[worker].checked for rows in snapshots]
            self.assertEqual(counts, sorted(counts))

    def test_early_match_and_password_only_for_matching_worker(self):
        snapshots, checked = [], []
        def check(target, raw):
            checked.append(raw)
            time.sleep(0.003)
            return raw == b'aa'
        with patch.object(HashTarget, 'matches', check):
            result = crack(HashTarget('md5', '0'*32), CrackConfig('abc', 2, 2, 2), on_progress=snapshots.append)
        self.assertEqual(result.password, 'aa')
        self.assertEqual(result.candidates_checked, len(checked))
        self.assertLess(len(checked), 9)
        self.assertEqual([row.found_password for row in snapshots[-1] if row.status == 'found'], ['aa'])
        self.assertTrue(all(row.found_password is None for row in snapshots[-1] if row.status != 'found'))

    def test_error_and_cancellation_cleanup_threads(self):
        before = {thread.ident for thread in threading.enumerate()}
        with patch.object(HashTarget, 'matches', side_effect=RuntimeError('verifier failed')):
            with self.assertRaisesRegex(RuntimeError, 'verifier failed'):
                crack(HashTarget('md5', '0'*32), CrackConfig('ab', 2, 2, 2))
        def cancel(rows):
            if any(row.status == 'running' for row in rows):
                raise KeyboardInterrupt
        def slow(target, raw):
            time.sleep(0.02)
            return False
        with patch.object(HashTarget, 'matches', slow), self.assertRaises(KeyboardInterrupt):
            crack(HashTarget('md5', '0'*32), CrackConfig('ab', 5, 5, 2), on_progress=cancel)
        self.assertEqual({thread.ident for thread in threading.enumerate()}, before)

    def test_cli_is_parameter_only_and_stdout_is_json(self):
        root = Path(__file__).resolve().parents[2]
        args = [sys.executable, str(root/'main.py'), hashlib.md5(b'ba', usedforsecurity=False).hexdigest(),
                '--alphabet', 'ab', '--min-length', '2', '--max-length', '2', '--workers', '2']
        process = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding='utf-8',
                                 env={**os.environ, 'PYTHONUTF8': '1'}, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)['password'], 'ba')
        self.assertIn('FOUND PASSWORD', process.stderr)
        self.assertIn('FOUND by worker', process.stderr)
        self.assertNotIn('\x1b', process.stderr)
        with patch('builtins.input', side_effect=AssertionError('no questions')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run([]), 0)
                self.assertIn('--gpu', output.getvalue())

    def test_cli_exit_codes_and_unsupported_options(self):
        target = hashlib.md5(b'c', usedforsecurity=False).hexdigest()
        args = [target, '--alphabet', 'ab', '--max-length', '1', '--no-progress']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run(args), 1)
            self.assertEqual(run(['bad-hash']), 2)
            self.assertEqual(run(args+['--workers', '0']), 2)
            with patch('lab3.src.cli.crack', side_effect=KeyboardInterrupt):
                self.assertEqual(run(args), 130)
            for option in ('--backend', '--interactive', '--prefix', '--gpu-batch-size', '--gpu-device'):
                with self.subTest(option=option), self.assertRaises(SystemExit) as error:
                    run(args+[option, '1'])
                self.assertEqual(error.exception.code, 2)

    def test_renderer_keeps_full_match_and_escapes_candidates(self):
        stream = io.StringIO()
        renderer = CliProgress(CrackConfig('ab', 1, 1, 2), stream=stream)
        renderer.ansi = True
        password = 'пароль'*20
        renderer((WorkerProgress(1, None, 0, 'waiting'), WorkerProgress(2, None, 0, 'waiting')))
        renderer((WorkerProgress(1, '\x1b[31m', 1, 'done'), WorkerProgress(2, password, 1, 'found')))
        output = stream.getvalue()
        self.assertIn('\x1b[', output)
        self.assertIn('FOUND by worker 2: '+json.dumps(password, ensure_ascii=True), output)
        self.assertNotIn('FOUND by worker 1', output)

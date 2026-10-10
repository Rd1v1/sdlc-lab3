import contextlib
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from lab3.src.progress import CliProgress
from lab3.src.models import CrackConfig
from lab3.src.hashes import HashTarget, TargetError
from lab3.src.cpu import crack
from lab3.src.cli import run


ROOT = Path(__file__).resolve().parents[2]


class WorkerTests(unittest.TestCase):
    def test_both_backends_all_hashes_and_worker_counts(self):
        import bcrypt
        from argon2 import PasswordHasher
        hashes = [hashlib.md5(b'ba', usedforsecurity=False).hexdigest(),
                  hashlib.sha1(b'ba', usedforsecurity=False).hexdigest(),
                  bcrypt.hashpw(b'ba', bcrypt.gensalt(rounds=4)).decode(),
                  PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash('ba')]
        for backend in ('threads', 'processes'):
            for workers in (1, 2):
                for encoded in hashes:
                    with self.subTest(backend=backend, workers=workers, hash=encoded):
                        result = crack(HashTarget.parse(encoded), CrackConfig('ab', 1, 2, workers=workers, backend=backend))
                        self.assertEqual(result.password, 'ba')
                        self.assertTrue(result.found)
                        self.assertEqual(result.backend, backend)
                        self.assertEqual(result.workers, workers)
                        self.assertLessEqual(result.candidates_checked, result.total_candidates)

    def test_exhaustion_and_exact_worker_partition(self):
        from lab3.src.candidates import iter_candidates
        candidates = list(iter_candidates(CrackConfig('abc', 1, 3)))
        target = HashTarget.parse(hashlib.sha1(b'outside', usedforsecurity=False).hexdigest())
        for backend in ('threads', 'processes'):
            snapshots = []
            config = CrackConfig('abc', 1, 3, workers=2, backend=backend)
            result = crack(target, config, on_progress=snapshots.append)
            self.assertFalse(result.found)
            self.assertEqual(result.candidates_checked, 39)
            final = snapshots[-1]
            self.assertEqual([row.checked for row in final], [19, 20])
            self.assertEqual([row.candidate for row in final], [candidates[18], candidates[38]])
            self.assertEqual([row.status for row in final], ['done', 'done'])
            self.assertEqual([row.worker for row in final], [1, 2])

    def test_more_workers_than_candidates(self):
        target = HashTarget.parse(hashlib.md5(b'outside', usedforsecurity=False).hexdigest())
        snapshots = []
        result = crack(target, CrackConfig('a', 1, 1, workers=2, backend='processes'), snapshots.append)
        self.assertEqual(result.candidates_checked, 1)
        self.assertEqual(sum(row.checked for row in snapshots[-1]), 1)
        self.assertTrue(all(row.status == 'done' for row in snapshots[-1]))

    def test_live_candidates_are_real_and_counts_monotonic(self):
        snapshots = []
        def slow_match(target, candidate):
            time.sleep(0.012)
            return False
        with patch.object(HashTarget, 'matches', slow_match):
            crack(HashTarget('md5', '0' * 32), CrackConfig('ab', 5, 5, workers=2), snapshots.append)
        self.assertTrue(any(row.status == 'running' for rows in snapshots for row in rows))
        for worker in range(2):
            counts = [rows[worker].checked for rows in snapshots]
            self.assertEqual(counts, sorted(counts))
        self.assertTrue(all(row.candidate is None or (len(row.candidate) == 5 and set(row.candidate) <= set('ab'))
                            for rows in snapshots for row in rows))

    def test_early_success_counts_completed_checks_and_stops(self):
        calls = []
        lock = threading.Lock()
        def found(target, candidate):
            time.sleep(0.002)
            with lock:
                calls.append(candidate)
            return candidate == 'aa'
        with patch.object(HashTarget, 'matches', found):
            result = crack(HashTarget('md5', '0' * 32), CrackConfig('abc', 2, 2, workers=2))
        self.assertEqual(result.password, 'aa')
        self.assertEqual(result.candidates_checked, len(calls))
        self.assertLess(result.candidates_checked, 9)

    def test_cancellation_cleans_spawned_processes(self):
        import bcrypt
        target = HashTarget.parse(bcrypt.hashpw(b'outside', bcrypt.gensalt(rounds=8)).decode())
        existing = {process.pid for process in multiprocessing.active_children()}
        def cancel_when_running(rows):
            if any(row.status == 'running' for row in rows):
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            crack(target, CrackConfig('ab', 5, 5, workers=2, backend='processes'), cancel_when_running)
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, existing)

    def test_worker_error_cleans_threads(self):
        before = {thread.ident for thread in threading.enumerate()}
        with patch.object(HashTarget, 'matches', side_effect=RuntimeError('verifier failed')):
            with self.assertRaisesRegex(RuntimeError, 'verifier failed'):
                crack(HashTarget('md5', '0' * 32), CrackConfig('ab', 2, 2, workers=2))
        self.assertEqual({thread.ident for thread in threading.enumerate()}, before)

    def test_invalid_worker_options_and_control_characters(self):
        for config in (CrackConfig('ab', 1, 1, workers=0), CrackConfig('ab', 1, 1, workers=65),
                       CrackConfig('ab', 1, 1, backend='hybrid'), CrackConfig('a\x1b', 1, 1)):
            with self.assertRaises(ValueError):
                config.validate()
        with self.assertRaises(TargetError):
            crack(HashTarget('sha1', '0' * 32), CrackConfig('ab', 1, 1))

    def test_cli_process_progress_keeps_stdout_json(self):
        target = hashlib.md5(b'ba', usedforsecurity=False).hexdigest()
        process = subprocess.run([sys.executable, str(ROOT / 'main.py'), target,
                                  '--alphabet', 'ab', '--max-length', '2', '--workers', '2',
                                  '--backend', 'processes', '--progress'], cwd=ROOT,
                                 capture_output=True, text=True, encoding='utf-8', timeout=30,
                                 env={**os.environ, 'PYTHONUTF8': '1'})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)['password'], 'ba')
        self.assertIn('WORKER', process.stderr)
        self.assertIn('CANDIDATE', process.stderr)
        self.assertNotIn('\x1b', process.stderr)

    def test_interactive_mode_and_eof(self):
        target = hashlib.md5(b'b', usedforsecurity=False).hexdigest()
        args = [target, '--alphabet', 'ab', '--max-length', '1', '--interactive', '--no-progress']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with patch('builtins.input', side_effect=['threads', '2']):
                self.assertEqual(run(args), 0)
            with patch('builtins.input', side_effect=EOFError):
                self.assertEqual(run(args), 130)

    @unittest.skipUnless(os.name == 'posix', 'Console process-group SIGINT test requires POSIX')
    def test_cli_sigint_stops_parent_and_children(self):
        import bcrypt
        import signal
        target = bcrypt.hashpw(b'outside', bcrypt.gensalt(rounds=8)).decode()
        process = subprocess.Popen([sys.executable, str(ROOT / 'main.py'), target,
                                    '--alphabet', 'abcd', '--min-length', '6', '--max-length', '6',
                                    '--workers', '2', '--backend', 'processes', '--progress'],
                                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', start_new_session=True)
        try:
            time.sleep(0.6)
            os.killpg(process.pid, signal.SIGINT)
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 130, stderr)
            self.assertIn('Перебор прерван', stderr)
            self.assertEqual(stdout, '')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()

    def test_renderer_terminal_and_safe_unicode(self):
        from lab3.src.models import WorkerProgress
        stream = io.StringIO()
        renderer = CliProgress(CrackConfig('я', 1, 1), stream=stream)
        renderer.ansi = True
        renderer((WorkerProgress(1, None, 0, 'waiting'),))
        renderer((WorkerProgress(1, 'я', 1, 'found'),))
        self.assertIn('\x1b[', stream.getvalue())
        self.assertIn('"\\u044f"', stream.getvalue())


if __name__ == '__main__':
    unittest.main()

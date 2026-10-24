"""Снимок состояния воркеров и итоговая таблица на stderr."""
from __future__ import annotations

import json
import sys
import threading
import time
from .models import CrackConfig, WorkerProgress


class CliProgress:
    def __init__(self, config: CrackConfig, stream=None, total_candidates=None):
        self.backend = 'gpu' if config.gpu else 'cpu'
        self.workers = config.workers
        self.stream = sys.stderr if stream is None else stream
        self.total = total_candidates
        self.started = time.perf_counter()
        self.rows = tuple(WorkerProgress(index + 1, None, 0, 'waiting') for index in range(self.workers))
        self.cancelled = threading.Event()
        self.interactive = self.stream.isatty() and sys.stdin.isatty()

    def __call__(self, rows):
        self.rows = rows
        if self.cancelled.is_set():
            raise KeyboardInterrupt

    def summary(self):
        checked = sum(row.checked for row in self.rows)
        elapsed = time.perf_counter() - self.started
        count = f'{checked}/{self.total}' if self.total is not None else str(checked)
        return f'{self.backend} | workers={self.workers} | {elapsed:.1f}s | {count} checked | {checked / max(elapsed, 1e-9):.0f} checks/s'

    def table(self):
        def cell(value):
            return json.dumps(value, ensure_ascii=True) if value is not None else '-'
        values = [(row, cell(row.candidate), cell(row.found_password)) for row in self.rows]
        candidate_width = max(20, max((len(candidate) for _, candidate, _ in values), default=0))
        header = f'WORKER  STATE        CHECKED  {"CANDIDATE":<{candidate_width}}  FOUND PASSWORD'
        body = '\n'.join(f'{row.worker:>6}  {row.status:<8}  {row.checked:>10}  {candidate:<{candidate_width}}  {found}'
                         for row, candidate, found in values)
        return header, body

    def print_result(self):
        print(self.summary(), *self.table(), sep='\n', file=self.stream)
        for row in self.rows:
            if row.found_password is not None:
                print(f'FOUND by worker {row.worker}: {json.dumps(row.found_password, ensure_ascii=True)}', file=self.stream)
        self.stream.flush()

    def run(self, search):
        try:
            if self.interactive:
                from .terminal import WorkerTerminal, terminal_output
                with terminal_output(self.stream) as output:
                    return WorkerTerminal(self, search, output=output).run()
            return search(self)
        finally:
            self.print_result()

"""Таблица текущих кандидатов и результатов CPU/GPU-воркеров."""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from .models import CrackConfig


class CliProgress:
    """Render sampled worker state on stderr, leaving stdout as machine-readable JSON."""
    def __init__(self, config: CrackConfig, stream=None, total_candidates=None):
        self.config = config
        self.backend = 'gpu' if config.gpu else 'cpu'
        self.workers = config.workers
        self.stream = sys.stderr if stream is None else stream
        self.total = total_candidates
        self.started = time.perf_counter()
        self.last_render = 0.0
        self.previous = None
        self.lines = 0
        self.ansi = self.stream.isatty() and os.environ.get("TERM") != "dumb"
        if self.workers + 3 >= shutil.get_terminal_size((100, 24)).lines:
            self.ansi = False  # Full snapshots when the table cannot fit on one screen.
        if self.ansi and os.name == "nt":
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.restype = ctypes.c_void_p
            handle = kernel.GetStdHandle(-12)
            mode = ctypes.c_ulong()
            self.ansi = bool(kernel.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode))
                             and kernel.SetConsoleMode(ctypes.c_void_p(handle), mode.value | 4))

    def __call__(self, rows):
        now = time.perf_counter()
        final = all(row.status not in ("waiting", "running") for row in rows)
        if self.previous == rows or (not final and now - self.last_render < 0.1):
            return
        self.previous = rows
        self.last_render = now
        checked = sum(row.checked for row in rows)
        elapsed = now - self.started
        width = max(40, shutil.get_terminal_size((100, 24)).columns - 1)
        bar_size = 20
        speed = f"{checked / max(elapsed, 1e-9):.0f} checks/s"
        if self.total:
            filled = min(bar_size, int(bar_size * checked / self.total))
            progress = (f"[{'#' * filled}{'-' * (bar_size - filled)}] {checked}/{self.total} "
                        f"({100 * checked / self.total:.1f}%) | {speed}")
        else:
            progress = f"{checked} checked | {speed}"
        lines = [f"{self.backend} | workers={self.workers} | {elapsed:.1f}s", progress,
                 "WORKER  STATE     CHECKED  CANDIDATE (sample)       FOUND PASSWORD"]
        text_width = max(4, (width - 28) // 2)
        def cell(value):
            text = json.dumps(value, ensure_ascii=True) if value is not None else "-"
            return text if len(text) <= text_width else text[:text_width - 3] + "..."
        for row in rows:
            lines.append(f"{row.worker:>6}  {row.status:<8}  {row.checked:>7}  "
                         f"{cell(row.candidate):<{text_width}} {cell(row.found_password)}")
        if self.ansi and self.lines:
            self.stream.write(f"\x1b[{self.lines}A")
        for line in lines:
            self.stream.write(("\x1b[2K" if self.ansi else "") + line[:width] + "\n")
        self.stream.flush()
        self.lines = len(lines)
        if final:
            for row in rows:
                if row.found_password is not None:
                    print(f"FOUND by worker {row.worker}: {json.dumps(row.found_password, ensure_ascii=True)}",
                          file=self.stream, flush=True)
                    self.lines += 1


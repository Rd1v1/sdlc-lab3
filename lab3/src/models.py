"""Параметры поиска, результат и состояние воркера."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CrackConfig:
    alphabet: str
    min_length: int
    max_length: int
    candidate_limit: int = 2_000_000
    workers: int = 1
    backend: str = "threads"
    prefix: str = ""

    def validate(self) -> int:
        if not self.alphabet or len(self.alphabet) > 128 or len(set(self.alphabet)) != len(self.alphabet):
            raise ValueError("Алфавит должен содержать 1-128 уникальных символов")
        if not 1 <= self.min_length <= self.max_length <= 8:
            raise ValueError("Длины кандидатов должны находиться в диапазоне 1-8")
        if self.candidate_limit < 1:
            raise ValueError("Лимит кандидатов должен быть положительным")
        if not 1 <= self.workers <= min(64, os.cpu_count() or 1):
            raise ValueError("Число воркеров должно быть от 1 до числа логических процессоров (максимум 64)")
        if self.backend not in ("threads", "processes"):
            raise ValueError("Режим воркеров: threads или processes")
        if self.backend == "processes" and os.name == "nt" and self.workers > 61:
            raise ValueError("На Windows допускается не более 61 процесса")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.alphabet):
            raise ValueError("Управляющие символы в алфавите запрещены")
        if len(self.prefix) > 64 or any(ord(character) < 32 or ord(character) == 127 for character in self.prefix):
            raise ValueError("Префикс: максимум 64 символа без управляющих символов")
        count = sum(len(self.alphabet) ** length for length in range(self.min_length, self.max_length + 1))
        if count > self.candidate_limit:
            raise ValueError(f"Диапазон содержит {count:,} кандидатов, лимит: {self.candidate_limit:,}")
        return count


@dataclass(frozen=True)
class CrackResult:
    found: bool
    password: str | None
    elapsed_seconds: float
    candidates_checked: int
    total_candidates: int
    workers: int
    backend: str = "threads"
    password_hex: str | None = None


@dataclass(frozen=True)
class WorkerProgress:
    worker: int
    candidate: str | None
    checked: int
    status: str


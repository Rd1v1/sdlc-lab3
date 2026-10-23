"""Параметры, результат поиска и строка таблицы воркеров."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CrackConfig:
    alphabet: str = '0123456789'
    min_length: int = 1
    max_length: int = 6
    workers: int = 1
    gpu: bool = False

    def validate(self, wordlist: Path | None = None) -> int | None:
        maximum = 4096 if self.gpu else min(64, os.cpu_count() or 1)
        if not 1 <= self.workers <= maximum:
            raise ValueError(f'Число воркеров должно быть от 1 до {maximum}')
        if wordlist is not None:
            if not wordlist.is_file() or wordlist.stat().st_size > 256 * 1024 * 1024:
                raise ValueError('Словарь должен быть файлом размером не более 256 МиБ')
            return None
        if not self.alphabet or len(self.alphabet) > 128 or len(set(self.alphabet)) != len(self.alphabet):
            raise ValueError('Алфавит: от 1 до 128 уникальных символов')
        if any(ord(char) < 32 or ord(char) == 127 for char in self.alphabet):
            raise ValueError('Управляющие символы в алфавите запрещены')
        if not 1 <= self.min_length <= self.max_length <= 8:
            raise ValueError('Длины должны находиться в диапазоне 1–8')
        total = sum(len(self.alphabet) ** size for size in range(self.min_length, self.max_length + 1))
        if total > 2_000_000:
            raise ValueError('Учебный предел — 2 млн кандидатов')
        return total


@dataclass(frozen=True)
class CrackResult:
    found: bool
    password: str | None
    elapsed_seconds: float
    candidates_checked: int
    total_candidates: int | None
    workers: int
    backend: str
    password_hex: str | None = None
    rejected: int = 0
    gpu_kernel_seconds: float | None = None


@dataclass(frozen=True)
class WorkerProgress:
    worker: int
    candidate: str | None
    checked: int
    status: str

    @property
    def found_password(self) -> str | None:
        return self.candidate if self.status == 'found' else None

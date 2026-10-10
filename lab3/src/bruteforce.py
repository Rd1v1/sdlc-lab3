from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator


class TargetError(ValueError):
    pass


@dataclass(frozen=True)
class HashTarget:
    algorithm: str
    encoded: str

    @classmethod
    def parse(cls, encoded: str) -> HashTarget:
        value = encoded.strip()
        if re.fullmatch(r"[0-9a-fA-F]{32}", value):
            return cls("md5", value.lower())
        if re.fullmatch(r"[0-9a-fA-F]{40}", value):
            return cls("sha1", value.lower())
        if value.startswith(("$2a$", "$2b$", "$2y$")):
            match = re.fullmatch(r"\$2[aby]\$(\d\d)\$[./A-Za-z0-9]{53}", value)
            if not match or not 4 <= int(match.group(1)) <= 12:
                raise TargetError("Некорректный bcrypt-хэш или cost вне учебного предела 4-12")
            return cls("bcrypt", value)
        if value.startswith("$argon2id$"):
            match = re.fullmatch(r"\$argon2id\$v=19\$m=(\d+),t=(\d+),p=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)", value)
            if not match or len(value) > 512:
                raise TargetError("Некорректный Argon2id-хэш")
            memory_kib, iterations, parallelism = map(int, match.groups()[:3])
            if not 8 <= memory_kib <= 262144 or not 1 <= iterations <= 10 or not 1 <= parallelism <= 8:
                raise TargetError("Параметры Argon2id выходят за установленный предел")
            if memory_kib < 8 * parallelism:
                raise TargetError("Argon2id memory must be at least 8 * parallelism")
            try:
                salt, digest = [base64.b64decode(part + '=' * (-len(part) % 4), validate=True) for part in match.groups()[3:]]
            except binascii.Error as error:
                raise TargetError("Некорректная base64 в Argon2id") from error
            if not 8 <= len(salt) <= 64 or not 4 <= len(digest) <= 64:
                raise TargetError("Некорректные длины salt/hash Argon2id")
            return cls("argon2id", value)
        raise TargetError("Поддерживаются только MD5, SHA-1, bcrypt и Argon2id")

    def matches(self, candidate: str) -> bool:
        if self.algorithm not in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            raise TargetError("Неподдерживаемый алгоритм")
        raw = candidate.encode("utf-8")
        if self.algorithm == "md5":
            return hashlib.md5(raw, usedforsecurity=False).hexdigest() == self.encoded
        if self.algorithm == "sha1":
            return hashlib.sha1(raw, usedforsecurity=False).hexdigest() == self.encoded
        if self.algorithm == "bcrypt":
            if len(raw) > 72:
                return False
            try:
                import bcrypt
            except ImportError as error:
                raise RuntimeError("Для bcrypt активируйте .venv и установите requirements.txt") from error
            return bcrypt.checkpw(raw, self.encoded.encode("ascii"))
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerificationError, VerifyMismatchError
        except ImportError as error:
            raise RuntimeError("Для Argon2 активируйте .venv и установите requirements.txt") from error
        try:
            return PasswordHasher().verify(self.encoded, candidate)
        except VerifyMismatchError:
            return False
        except VerificationError as error:
            raise TargetError("Argon2id-хэш повреждён или не поддерживается") from error


@dataclass(frozen=True)
class CrackConfig:
    alphabet: str
    min_length: int
    max_length: int
    candidate_limit: int = 2_000_000
    workers: int = 1

    def validate(self) -> int:
        if not self.alphabet or len(self.alphabet) > 128 or len(set(self.alphabet)) != len(self.alphabet):
            raise ValueError("Алфавит должен содержать 1-128 уникальных символов")
        if not 1 <= self.min_length <= self.max_length <= 8:
            raise ValueError("Длины кандидатов должны находиться в диапазоне 1-8")
        if self.candidate_limit < 1:
            raise ValueError("Лимит кандидатов должен быть положительным")
        if not 1 <= self.workers <= min(64, os.cpu_count() or 1):
            raise ValueError("Число потоков должно быть от 1 до числа логических процессоров (максимум 64)")
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


def candidate_at(index: int, alphabet: str, length: int) -> str:
    if not alphabet or length < 1 or not 0 <= index < len(alphabet) ** length:
        raise ValueError("Индекс кандидата вне пространства перебора")
    base = len(alphabet)
    characters = [alphabet[0]] * length
    for position in range(length - 1, -1, -1):
        index, digit = divmod(index, base)
        characters[position] = alphabet[digit]
    return "".join(characters)


def iter_candidates(config: CrackConfig) -> Iterator[str]:
    config.validate()
    for length in range(config.min_length, config.max_length + 1):
        for index in range(len(config.alphabet) ** length):
            yield candidate_at(index, config.alphabet, length)


def crack(target: HashTarget, config: CrackConfig) -> CrackResult:
    total = config.validate()
    started = time.perf_counter()
    if config.workers == 1:
        checked = 0
        for candidate in iter_candidates(config):
            checked += 1
            if target.matches(candidate):
                return CrackResult(True, candidate, time.perf_counter() - started, checked, total, 1)
        return CrackResult(False, None, time.perf_counter() - started, checked, total, 1)

    import threading

    stopped = threading.Event()

    def scan(length: int, start: int, end: int) -> tuple[str | None, int]:
        checked = 0
        for index in range(start, end):
            if stopped.is_set():
                break
            checked += 1
            candidate = candidate_at(index, config.alphabet, length)
            if target.matches(candidate):
                stopped.set()
                return candidate, checked
        return None, checked

    futures = []
    with ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="candidate-check") as executor:
        for length in range(config.min_length, config.max_length + 1):
            count = len(config.alphabet) ** length
            chunk_size = max(1, (count + config.workers * 4 - 1) // (config.workers * 4))
            for start in range(0, count, chunk_size):
                futures.append(executor.submit(scan, length, start, min(start + chunk_size, count)))
        checked = 0
        password = None
        try:
            for future in as_completed(futures):
                try:
                    found, attempts = future.result()
                except CancelledError:
                    continue
                checked += attempts
                if found is not None and password is None:
                    password = found
                    stopped.set()
                    for pending in futures:
                        pending.cancel()
        finally:
            stopped.set()
            for pending in futures:
                pending.cancel()
    return CrackResult(password is not None, password, time.perf_counter() - started, checked, total, config.workers)


HASHCAT_MODES = {"md5": "0", "sha1": "100", "bcrypt": "3200", "argon2id": "34000"}


def compare_hashcat(target: HashTarget, config: CrackConfig, executable: str = "hashcat") -> dict[str, object]:
    binary = shutil.which(executable)
    if binary is None:
        return {"available": False, "reason": "hashcat is not installed", "elapsed_seconds": None}
    binary = str(Path(binary).resolve())
    mode = HASHCAT_MODES.get(target.algorithm)
    if mode is None:
        return {"available": False, "reason": f"No verified hashcat mode configured for {target.algorithm}", "elapsed_seconds": None}
    config.validate()
    scratch = Path(__file__).resolve().parents[2] / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lab3-hashcat-", dir=scratch) as directory:
        target_file = Path(directory) / "target.hash"
        wordlist = Path(directory) / "candidates.txt"
        cracked_file = Path(directory) / "cracked.txt"
        target_file.write_text(target.encoded + "\n", encoding="ascii")
        with wordlist.open("w", encoding="utf-8", newline="\n") as output:
            for candidate in iter_candidates(config):
                output.write(candidate + "\n")
        command = [
            binary,
            "--quiet",
            "--potfile-disable",
            "--restore-disable",
            "--logfile-disable",
            "--outfile", str(cracked_file),
            "--outfile-format", "2",
            "-m", mode,
            "-a", "0",
            str(target_file),
            str(wordlist),
        ]
        started = time.perf_counter()
        process = subprocess.run(command, cwd=Path(binary).parent, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=300, check=False)
        elapsed = time.perf_counter() - started
        output_text = process.stdout + process.stderr
        if process.returncode not in (0, 1):
            return {"available": True, "supported": False, "reason": output_text.strip()[-1000:], "elapsed_seconds": elapsed}
        return {
            "available": True,
            "supported": True,
            "cracked": cracked_file.exists() and any(target.matches(line) for line in cracked_file.read_text(encoding='utf-8').splitlines()),
            "elapsed_seconds": elapsed,
            "command": f"hashcat --potfile-disable --restore-disable --logfile-disable -m {mode} -a 0 target.hash candidates.txt",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Учебный локальный перебор тестовых хэшей")
    parser.add_argument("target", help="Локальный тестовый hash string")
    parser.add_argument("--alphabet", default="0123456789")
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=6)
    parser.add_argument("--candidate-limit", type=int, default=2_000_000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--compare-hashcat", action="store_true")
    return parser


def run(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    try:
        target = HashTarget.parse(options.target)
        config = CrackConfig(options.alphabet, options.min_length, options.max_length, options.candidate_limit, options.workers)
        result = crack(target, config)
        report: dict[str, object] = {"algorithm": target.algorithm, **asdict(result)}
        if options.compare_hashcat:
            report["hashcat"] = compare_hashcat(target, config)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if result.found else 1
    except KeyboardInterrupt:
        print("Перебор прерван", file=sys.stderr)
        return 130
    except (TargetError, ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())

"""Разбор хэшей и проверка кандидата четырьмя алгоритмами."""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass


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
            if not match:
                raise TargetError("Некорректный bcrypt-хэш")
            if not 4 <= int(match.group(1)) <= 12:
                raise TargetError("Параметр сложности bcrypt (cost) вне диапазона 4-12, поддерживаемого приложением")
            return cls("bcrypt", value)
        if value.startswith("$argon2id$"):
            match = re.fullmatch(r"\$argon2id\$v=19\$m=(\d+),t=(\d+),p=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)", value)
            if not match or len(value) > 512:
                raise TargetError("Некорректный Argon2id-хэш")
            memory_kib, iterations, parallelism = map(int, match.groups()[:3])
            if not 8 <= memory_kib <= 262144 or not 1 <= iterations <= 10 or not 1 <= parallelism <= 8:
                raise TargetError("Параметры Argon2id выходят за диапазон, поддерживаемый приложением")
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

    def matches(self, candidate: str | bytes) -> bool:
        if self.algorithm not in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            raise TargetError("Неподдерживаемый алгоритм")
        raw = candidate.encode("utf-8") if isinstance(candidate, str) else candidate
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


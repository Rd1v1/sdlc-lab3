"""Генерация кандидатов и доступ к ним по индексу."""
from __future__ import annotations

from typing import Iterator
from .models import CrackConfig


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
            yield config.prefix + candidate_at(index, config.alphabet, length)


def _candidate_global(index: int, config: CrackConfig) -> str:
    for length in range(config.min_length, config.max_length + 1):
        count = len(config.alphabet) ** length
        if index < count:
            return config.prefix + candidate_at(index, config.alphabet, length)
        index -= count
    raise ValueError("Индекс вне пространства перебора")


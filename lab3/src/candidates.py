"""Поток кандидатов: полный перебор или строки словаря без перекодирования."""
from itertools import product
from pathlib import Path
from .models import CrackConfig


def iter_candidates(config: CrackConfig, wordlist: Path | None = None):
    if wordlist is not None:
        with wordlist.open('rb') as stream:
            for line in stream:
                yield line.removesuffix(b'\n').removesuffix(b'\r')
    else:
        for size in range(config.min_length, config.max_length + 1):
            for characters in product(config.alphabet, repeat=size):
                yield ''.join(characters).encode('utf-8')

"""Совместимый вход для прежних импортов и python -m lab3.src.bruteforce.

Реализация находится в отдельных модулях; этот файл только экспортирует API.
"""
from .candidates import candidate_at, iter_candidates
from .cli import build_parser, run
from .cpu import crack
from .hashes import HashTarget, TargetError
from .models import CrackConfig, CrackResult, WorkerProgress
from .progress import CliProgress
from .wordlist import crack_wordlist, inspect_wordlist

__all__ = [
    'candidate_at', 'iter_candidates', 'build_parser', 'run', 'crack',
    'HashTarget', 'TargetError',
    'CrackConfig', 'CrackResult', 'WorkerProgress', 'CliProgress',
    'crack_wordlist', 'inspect_wordlist',
]

if __name__ == '__main__':
    raise SystemExit(run())

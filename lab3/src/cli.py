"""Аргументы командной строки и выбор режима поиска."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from .cpu import crack
from .hashcat import compare_hashcat
from .hashes import HashTarget, TargetError
from .models import CrackConfig
from .progress import CliProgress
from .wordlist import crack_wordlist, inspect_wordlist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Учебный локальный перебор тестовых хэшей")
    parser.add_argument("target", help="Локальный тестовый hash string")
    parser.add_argument("--alphabet", default="0123456789")
    parser.add_argument("--prefix", default="", help="Известный префикс; длины относятся к перебираемой части")
    parser.add_argument("--wordlist", type=Path, help="Поиск по словарю; GPU или один CPU-поток")
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=6)
    parser.add_argument("--candidate-limit", type=int, default=2_000_000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--backend", choices=("threads", "processes", "gpu"), default="threads")
    parser.add_argument("--gpu-batch-size", type=int, default=16, help="Число GPU-кандидатов в пакете")
    parser.add_argument("--gpu-device", type=int, default=0, help="Индекс GPU OpenCL, начиная с 0")
    parser.add_argument("--gpu-wordlist-lines", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--interactive", action="store_true", help="Запросить режим и число воркеров")
    progress = parser.add_mutually_exclusive_group()
    progress.add_argument("--progress", dest="progress", action="store_true", help="Показать кандидатов воркеров в stderr")
    progress.add_argument("--no-progress", dest="progress", action="store_false", help="Отключить таблицу воркеров")
    parser.set_defaults(progress=None)
    parser.add_argument("--compare-hashcat", action="store_true")
    parser.add_argument("--hashcat-device", choices=('auto', 'cpu', 'gpu'), default='auto')
    return parser


def run(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    try:
        target = HashTarget.parse(options.target)
        if options.interactive:
            print("Режим: threads / processes / gpu", file=sys.stderr)
            print("Режим [threads]: ", end="", file=sys.stderr, flush=True)
            options.backend = input().strip() or "threads"
            if options.backend == 'gpu':
                print("Кандидатов в GPU-пакете [16]: ", end="", file=sys.stderr, flush=True)
                options.gpu_batch_size = int(input().strip() or "16")
            else:
                print("Число воркеров [1]: ", end="", file=sys.stderr, flush=True)
                options.workers = int(input().strip() or "1")
        config = CrackConfig(options.alphabet, options.min_length, options.max_length,
                             options.candidate_limit, options.workers,
                             'threads' if options.backend == 'gpu' else options.backend, options.prefix)
        enabled = sys.stderr.isatty() if options.progress is None else options.progress
        if options.backend == 'gpu':
            from .gpu import search_gpu
            if options.workers != 1:
                raise ValueError('Для GPU используйте --gpu-batch-size; --workers относится к CPU')
            if options.wordlist and options.prefix:
                raise ValueError('Префикс не применяется к словарю')
            def gpu_progress(rows):
                if enabled:
                    print('GPU | CANDIDATES IN CURRENT BATCH', file=sys.stderr)
                    for row in rows:
                        print(f'GPU worker {row.worker}: {json.dumps(row.candidate, ensure_ascii=True)} [{row.status}]', file=sys.stderr)
            result = search_gpu(target, config, options.wordlist, options.gpu_batch_size, options.gpu_device,
                                gpu_progress if enabled else None, options.gpu_wordlist_lines)
        elif options.wordlist:
            if config.workers != 1 or config.backend != 'threads' or config.prefix:
                raise ValueError('Словарь использует один поток без префикса: --workers 1 --backend threads')
            info = inspect_wordlist(options.wordlist)
            result = crack_wordlist(target, options.wordlist, metadata=info,
                                    on_progress=CliProgress(config, total_candidates=info['lines']) if enabled else None)
        else:
            result = crack(target, config, on_progress=CliProgress(config) if enabled else None)
        report: dict[str, object] = {"algorithm": target.algorithm, **(result if isinstance(result, dict) else asdict(result))}
        if options.compare_hashcat:
            report["hashcat"] = compare_hashcat(target, config, device_type=options.hashcat_device,
                                                attack='wordlist' if options.wordlist else 'mask', wordlist=options.wordlist)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['found'] else 1
    except (KeyboardInterrupt, EOFError):
        print("Перебор прерван", file=sys.stderr)
        return 130
    except (TargetError, ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


"""Аргументы командной строки и выбор режима поиска."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from .cpu import crack
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
    parser.add_argument("--workers", type=int, help="Число CPU-воркеров или кандидатов в GPU-пакете")
    parser.add_argument("--backend", choices=("threads", "processes", "gpu"), default="threads")
    parser.add_argument("--gpu-batch-size", type=int, help="GPU: синоним --workers (по умолчанию 16)")
    parser.add_argument("--gpu-device", type=int, default=0, help="Индекс GPU OpenCL, начиная с 0")
    parser.add_argument("--interactive", action="store_true", help="Запросить режим и число воркеров")
    progress = parser.add_mutually_exclusive_group()
    progress.add_argument("--progress", dest="progress", action="store_true", help="Показать кандидатов воркеров в stderr")
    progress.add_argument("--no-progress", dest="progress", action="store_false", help="Отключить таблицу воркеров")
    parser.set_defaults(progress=None)
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
                print("Число GPU-воркеров (кандидатов в пакете) [16]: ", end="", file=sys.stderr, flush=True)
                options.workers = int(input().strip() or "16")
            else:
                print("Число воркеров [1]: ", end="", file=sys.stderr, flush=True)
                options.workers = int(input().strip() or "1")
        if options.backend == 'gpu':
            if (options.workers is not None and options.gpu_batch_size is not None
                    and options.workers != options.gpu_batch_size):
                raise ValueError('--workers и --gpu-batch-size должны совпадать, если указаны вместе')
            batch_size = options.workers if options.workers is not None else options.gpu_batch_size
            batch_size = 16 if batch_size is None else batch_size
            if not 1 <= batch_size <= 4096:
                raise ValueError('Число GPU-воркеров должно быть от 1 до 4096')
        elif options.gpu_batch_size is not None:
            raise ValueError('--gpu-batch-size применяется только к --backend gpu')
        cpu_workers = 1 if options.backend == 'gpu' or options.workers is None else options.workers
        config = CrackConfig(options.alphabet, options.min_length, options.max_length,
                             options.candidate_limit, cpu_workers,
                             'threads' if options.backend == 'gpu' else options.backend, options.prefix)
        enabled = sys.stderr.isatty() if options.progress is None else options.progress
        if options.backend == 'gpu':
            from .gpu import search_gpu
            if options.wordlist and options.prefix:
                raise ValueError('Префикс не применяется к словарю')
            renderer = CliProgress(config, backend='gpu', workers=batch_size,
                                   total_candidates=0 if options.wordlist else None) if enabled else None
            result = search_gpu(target, config, options.wordlist, batch_size, options.gpu_device, renderer)
        elif options.wordlist:
            if config.workers != 1 or config.backend != 'threads' or config.prefix:
                raise ValueError('Словарь использует один поток без префикса: --workers 1 --backend threads')
            info = inspect_wordlist(options.wordlist)
            result = crack_wordlist(target, options.wordlist, metadata=info,
                                    on_progress=CliProgress(config, total_candidates=info['lines']) if enabled else None)
        else:
            result = crack(target, config, on_progress=CliProgress(config) if enabled else None)
        report: dict[str, object] = {"algorithm": target.algorithm, **(result if isinstance(result, dict) else asdict(result))}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['found'] else 1
    except (KeyboardInterrupt, EOFError):
        print("Перебор прерван", file=sys.stderr)
        return 130
    except (TargetError, ValueError, RuntimeError, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


"""Только параметры команды; основной режим CPU, --gpu включает видеокарту."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from .cpu import crack
from .hashes import HashTarget
from .models import CrackConfig
from .progress import CliProgress


def build_parser():
    parser = argparse.ArgumentParser(description='Моё приложение — офлайн-перебор учебного хэша')
    parser.add_argument('target', metavar='HASH')
    parser.add_argument('--alphabet', default='0123456789')
    parser.add_argument('--min-length', type=int, default=1)
    parser.add_argument('--max-length', type=int, default=6)
    parser.add_argument('--workers', type=int, default=1, help='Число CPU-потоков или кандидатов в GPU-пакете')
    parser.add_argument('--gpu', action='store_true', help='Вычислять хэши на первой доступной GPU')
    parser.add_argument('--wordlist', type=Path, help='Читать кандидаты из файла, например rockyou.txt')
    parser.add_argument('--no-progress', action='store_true', help='Отключить таблицу воркеров для замеров')
    return parser


def run(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    parser = build_parser()
    if not arguments:
        parser.print_help()
        return 0
    options = parser.parse_args(arguments)
    try:
        target = HashTarget.parse(options.target)
        config = CrackConfig(options.alphabet, options.min_length, options.max_length, options.workers, options.gpu)
        total = config.validate(options.wordlist)
        progress = None if options.no_progress else CliProgress(config, total_candidates=total)
        if options.gpu:
            from .gpu import search_gpu as search
        else:
            search = crack
        if progress is None:
            result = search(target, config, options.wordlist)
        else:
            result = progress.run(lambda callback: search(target, config, options.wordlist, on_progress=callback))
        print(json.dumps({'algorithm': target.algorithm, **asdict(result)}, ensure_ascii=False, indent=2))
        return 0 if result.found else 1
    except (KeyboardInterrupt, EOFError):
        print('Перебор прерван', file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, OSError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        return 2

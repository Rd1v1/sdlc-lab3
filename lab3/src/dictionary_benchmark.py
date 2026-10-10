"""Compare native mask brute force and the full RockYou file on the same target."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

from .benchmark import make_target
from .bruteforce import CrackConfig, crack, crack_wordlist, compare_hashcat, inspect_wordlist


def run(repeats, binary, wordlist, device_type='gpu'):
    if not 1 <= repeats <= 20:
        raise ValueError('repeats must be 1..20')
    info = inspect_wordlist(wordlist)
    password = '123456'
    position = None
    with wordlist.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            if line.removesuffix(b'\n').removesuffix(b'\r') == password.encode():
                position = number
                break
    if position is None:
        raise ValueError('Expected test password is absent from RockYou')
    config = CrackConfig('0123456789', 1, 1, workers=1, prefix='12345')
    rows = []
    external = []
    for algorithm in ('md5', 'sha1', 'bcrypt', 'argon2id'):
        target = make_target(algorithm, password)
        target.matches(password)  # Backend imports/warmup outside the search timer.
        for scenario in ('mask', 'rockyou'):
            for repeat in range(1, repeats + 1):
                command = [sys.executable, '-m', 'lab3.src.bruteforce', target.encoded, '--backend', 'gpu',
                           '--gpu-batch-size', '16', '--gpu-device', '0', '--no-progress']
                if scenario == 'mask':
                    command += ['--prefix', '12345', '--alphabet', '0123456789', '--min-length', '1', '--max-length', '1']
                else:
                    command += ['--wordlist', str(wordlist), '--gpu-wordlist-lines', str(info['lines'])]
                started = time.perf_counter()
                process = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
                                         capture_output=True, text=True, encoding='utf-8',
                                         env={**os.environ, 'PYTHONUTF8': '1'}, timeout=300, check=False)
                elapsed = time.perf_counter() - started
                if process.returncode:
                    raise RuntimeError(process.stderr)
                result = json.loads(process.stdout)
                if result['backend'] != 'gpu' or result['gpu_device']['type'] != 'GPU' or result['gpu_kernel_seconds'] <= 0:
                    raise RuntimeError('Own application did not execute verified GPU kernels')
                if result['password'] != password:
                    raise RuntimeError('Own application did not recover the expected password')
                measured = compare_hashcat(target, config, binary, device_type,
                                            attack='mask' if scenario == 'mask' else 'wordlist',
                                            wordlist=wordlist if scenario == 'rockyou' else None)
                if not measured.get('supported') or not measured.get('cracked'):
                    raise RuntimeError(f'{algorithm}/{scenario}: {measured}')
                rows.append(dict(scenario=scenario, algorithm=algorithm, repeat=repeat,
                                 target_hash=target.encoded, expected_password=password,
                                 total_search_space=result['total_candidates'], attempts=result['candidates_checked'],
                                 workers=result['workers'], backend='gpu', elapsed_seconds=elapsed,
                                 search_seconds=result['elapsed_seconds'], gpu_kernel_seconds=result['gpu_kernel_seconds'],
                                 gpu_device=result['gpu_device'], batch_size=result['batch_size']))
                external.append(dict(scenario=scenario, algorithm=algorithm, repeat=repeat,
                                     target_hash=target.encoded, expected_password=password, **measured))
                print(f'{algorithm}/{scenario}: repeat {repeat}/{repeats} complete', file=sys.stderr, flush=True)
    return dict(created_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                platform=platform.platform(), repeats=repeats, hashcat_device=device_type,
                password=password, mask='12345?d', known_prefix='12345', suffix_alphabet='0123456789',
                dictionary={**info, 'filename': 'rockyou.txt', 'target_line': position},
                results=rows, professional=external)


def render_report(report):
    lines = ['# LAB 3 — сравнение времени: без словаря и с rockyou.txt', '',
             f"Оба приложения выполняют хеширование на одной GPU — {report.get('gpu_device', report['results'][0]['gpu_device'])['name']} — через OpenCL. "
             'Замеры выполнены напрямую в Windows. '
             f"В каждой ячейке — медиана {report['repeats']} запусков для одного и того же учебного пароля `123456`.", '',
             '| Алгоритм | Моё приложение: без словаря, с | Моё приложение: rockyou.txt, с | Hashcat: без словаря, с | Hashcat: rockyou.txt, с |',
             '| --- | ---: | ---: | ---: | ---: |']
    for algorithm, label in (('md5', 'MD5'), ('sha1', 'SHA-1'), ('bcrypt', 'bcrypt'), ('argon2id', 'Argon2id')):
        values = []
        for rows, scenario in ((report['results'], 'mask'), (report['results'], 'rockyou'),
                               (report['professional'], 'mask'), (report['professional'], 'rockyou')):
            measured = [row['elapsed_seconds'] for row in rows if row['algorithm'] == algorithm and row['scenario'] == scenario]
            values.append(f'{statistics.median(measured):.6f}' if measured else 'нет замера')
        lines.append('| '+label+' | '+' | '.join(values)+' |')
    info = report['dictionary']
    lines += ['', 'Без словаря: известен префикс `12345`, перебирается последняя цифра от 0 до 9 '
              '(10 вариантов, маска `12345?d`). Моё приложение генерирует варианты в памяти; '
              'hashcat использует настоящий режим маски `-a 3`, без файла кандидатов. '
              'Этот замер относится к указанной маске, а не к полному перебору всех шестизначных паролей.', '',
              f"Со словарём: используется полный исходный `rockyou.txt` — {info['lines']:,} строк; "
              f"`123456` находится в строке {info['target_line']}. Моё приложение читает словарь потоково, "
              'hashcat работает в режиме `-a 0`. Поиск останавливается после находки: время не означает проверку всех строк.', '',
              'Для обоих инструментов измеряется время отдельного процесса от запуска до завершения: '
              'подготовка OpenCL, чтение кандидатов, передача данных и поиск включены. '
              'Моё приложение отправляет пакеты до 16 кандидатов на GPU; завершает уже начатый пакет перед проверкой результата. '
              'Параметры хэшей и наборы кандидатов одинаковы; GPU-запуски идут последовательно. '
              'Скачивание словаря, проверка его контрольной суммы и генерация хэшей выполняются до замера.', '',
              'bcrypt: cost=10. Argon2id: m=65536 КиБ, t=3, p=2. Соли одинаковы для обоих инструментов. '
              'На коротком поиске подготовка hashcat существенно влияет на время; таблица не оценивает пиковую скорость GPU.', '',
              '## Воспроизведение', '', '```powershell',
              '.venv/Scripts/python.exe scripts/setup-wordlist.py',
              'powershell -ExecutionPolicy Bypass -File scripts/benchmark-gpu.ps1 -Repeats 3',
              '```', '',
              'Исходные замеры: [JSON](reports/comparison-results.json), [Моё приложение](reports/comparison-results.csv), '
              '[hashcat](reports/hashcat-runs.csv). JSON содержит SHA-256 словаря, позицию пароля, подтверждение GPU-устройства '
              'и команды атак. Словарь хранится в `.tools/wordlists` и не включён в Git.', '',
              'GPU-бэкенд приложения управляет OpenCL напрямую через PyOpenCL. Криптографические примитивы '
              'заимствованы из hashcat 7.1.2 под MIT; [лицензия](lab3/src/kernels/vendor/LICENSE.txt) '
              'и [происхождение файлов](lab3/src/kernels/vendor/ORIGIN.json) сохранены. '
              'Генерация кандидатов, чтение словаря, передача буферов, запуск ядер и проверка результата реализованы в приложении; '
              'приложение не вызывает исполняемый файл hashcat для своего поиска.', '']
    return '\n'.join(lines)

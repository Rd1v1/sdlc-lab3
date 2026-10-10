"""Compare native mask brute force and the full RockYou file on the same target."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import sys

from .benchmark import make_target
from .bruteforce import CrackConfig, crack, crack_wordlist, compare_hashcat, inspect_wordlist


def run(repeats, binary, wordlist):
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
                result = crack(target, config) if scenario == 'mask' else crack_wordlist(target, wordlist, metadata=info)
                if result.password != password:
                    raise RuntimeError('Own application did not recover the expected password')
                measured = compare_hashcat(target, config, binary, 'cpu',
                                            attack='mask' if scenario == 'mask' else 'wordlist',
                                            wordlist=wordlist if scenario == 'rockyou' else None)
                if not measured.get('supported') or not measured.get('cracked'):
                    raise RuntimeError(f'{algorithm}/{scenario}: {measured}')
                rows.append(dict(scenario=scenario, algorithm=algorithm, repeat=repeat,
                                 target_hash=target.encoded, expected_password=password,
                                 total_search_space=result.total_candidates, attempts=result.candidates_checked,
                                 workers=1, backend='threads', elapsed_seconds=result.elapsed_seconds))
                external.append(dict(scenario=scenario, algorithm=algorithm, repeat=repeat,
                                     target_hash=target.encoded, expected_password=password, **measured))
                print(f'{algorithm}/{scenario}: repeat {repeat}/{repeats} complete', file=sys.stderr, flush=True)
    return dict(created_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                platform=platform.platform(), repeats=repeats, hashcat_device='cpu',
                password=password, mask='12345?d', known_prefix='12345', suffix_alphabet='0123456789',
                dictionary={**info, 'filename': 'rockyou.txt', 'target_line': position},
                results=rows, professional=external)


def render_report(report):
    lines = ['# LAB 3 — сравнение времени: без словаря и с rockyou.txt', '',
             'Оба инструмента измерены на CPU в одном контейнере, ограниченном одним логическим процессором. '
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
              'Моё приложение использует один поток. Время включает создание воркера, чтение кандидатов и поиск; '
              'у hashcat также учтены запуск процесса, подготовка OpenCL и индексация словаря. '
              'Скачивание словаря, проверка его контрольной суммы, генерация хэшей и сборка контейнера выполняются до замера.', '',
              'bcrypt: cost=10. Argon2id: m=65536 КиБ, t=3, p=2. Соли одинаковы для обоих инструментов. '
              'На коротком поиске подготовка hashcat существенно влияет на время; таблица не оценивает пиковую скорость CPU.', '',
              '## Нужен ли Docker для LAB 3', '',
              'По сохранённым требованиям LAB 3 Docker не обязателен: нужны собственный перебор, '
              'анализ скорости и сравнение с профессиональным инструментом. Приложение и тесты запускаются через локальную `.venv`. '
              'Docker требуется только для воспроизведения этих CPU-замеров: в текущей Windows-конфигурации hashcat не видит CPU OpenCL, '
              'поэтому оба инструмента запускаются вместе с PoCL в контейнере. При установленном CPU OpenCL можно работать без Docker. '
              'Актуальная страница задания на момент проверки недоступна.', '',
              '## Воспроизведение', '', '```powershell',
              '.venv/Scripts/python.exe scripts/setup-wordlist.py',
              'powershell -ExecutionPolicy Bypass -File scripts/benchmark-cpu.ps1 -Repeats 3 -Comparison dictionary',
              '```', '',
              'Исходные замеры: [JSON](reports/comparison-results.json), [Моё приложение](reports/comparison-results.csv), '
              '[hashcat](reports/hashcat-runs.csv). JSON содержит SHA-256 словаря, позицию пароля, подтверждение CPU-устройства '
              'и команды атак. Словарь хранится в `.tools/wordlists` и не включён в Git.', '']
    return '\n'.join(lines)

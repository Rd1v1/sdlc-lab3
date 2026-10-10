"""Controlled offline experiments; CSV contains every actual run, not estimates."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from .bruteforce import CrackConfig, HashTarget, crack, compare_hashcat


def make_target(algorithm, password):
    raw = password.encode('utf-8')
    if algorithm in ('md5', 'sha1'):
        return HashTarget.parse(hashlib.new(algorithm, raw, usedforsecurity=False).hexdigest())
    if algorithm == 'bcrypt':
        import bcrypt
        return HashTarget.parse(bcrypt.hashpw(raw, b'$2b$10$abcdefghijklmnopqrstuu').decode())
    from argon2.low_level import hash_secret, Type
    return HashTarget.parse(hash_secret(raw, b'saltsalt', 3, 65536, 2, 32, Type.ID).decode())


def run(repeats=3, include_hashcat=False, executable='hashcat', smoke=False, backend='threads', worker_counts=None):
    if not 1 <= repeats <= 20:
        raise ValueError('repeats must be 1..20')
    CrackConfig('abc', 1, 1, backend=backend).validate()
    if worker_counts is not None:
        if not worker_counts or len(set(worker_counts)) != len(worker_counts):
            raise ValueError('workers must be a nonempty list of unique counts')
        for workers in worker_counts:
            CrackConfig('abc', 1, 1, workers=workers, backend=backend).validate()
    # Change one variable at a time. Last-position scenarios exhaust their range.
    scenarios = [('base', 'abc', 1, 'c'), ('length2', 'abc', 2, 'cc'),
                 ('length3', 'abc', 3, 'ccc'), ('alphabet4', 'abcd', 2, 'dd'),
                 ('position_first', 'abc', 2, 'aa')]
    if smoke:
        scenarios = scenarios[:1]
    rows = []
    professional = []
    for scenario, alphabet, length, password in scenarios:
        for algorithm in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            target = make_target(algorithm, password)
            workers_set = (1, 2) if scenario in ('base', 'length2') and (os.cpu_count() or 1) >= 2 else (1,)
            if worker_counts is not None:
                workers_set = worker_counts
            for workers in workers_set:
                config = CrackConfig(alphabet, length, length, workers=workers, backend=backend)
                target.matches(password)  # Warm up imports/backends outside timing.
                for repeat in range(1, repeats + 1):
                    result = crack(target, config)
                    if result.password != password:
                        raise RuntimeError('Incorrect benchmark result')
                    rows.append(dict(scenario=scenario, algorithm=algorithm, alphabet=alphabet,
                                     alphabet_size=len(alphabet), password_length=length, expected_password=password,
                                     target_hash=target.encoded, total_search_space=result.total_candidates,
                                     workers=workers, backend=backend, repeat=repeat, elapsed_seconds=result.elapsed_seconds,
                                     attempts=result.candidates_checked,
                                     attempts_per_second=result.candidates_checked / result.elapsed_seconds))
            if include_hashcat and scenario in ('base', 'length2'):
                for repeat in range(1, repeats + 1):
                    measured = compare_hashcat(target, CrackConfig(alphabet, length, length), executable)
                    professional.append(dict(scenario=scenario, algorithm=algorithm, repeat=repeat, **measured))
            print(f'{scenario}: {algorithm} complete', file=sys.stderr, flush=True)
    if not smoke:
        for algorithm in ('md5', 'sha1'):
            for length in (4, 5):
                password = '9' * length
                target = make_target(algorithm, password)
                for workers in (worker_counts if worker_counts is not None else ((1, 2) if (os.cpu_count() or 1) >= 2 else (1,))):
                    for repeat in range(1, repeats + 1):
                        result = crack(target, CrackConfig('0123456789', length, length, workers=workers, backend=backend))
                        if result.password != password:
                            raise RuntimeError('Incorrect fast benchmark result')
                        rows.append(dict(scenario='fast' + str(length), algorithm=algorithm, alphabet='0123456789',
                                         alphabet_size=10, password_length=length, expected_password=password,
                                         target_hash=target.encoded, total_search_space=result.total_candidates,
                                         workers=workers, backend=backend, repeat=repeat, elapsed_seconds=result.elapsed_seconds,
                                         attempts=result.candidates_checked,
                                         attempts_per_second=result.candidates_checked / result.elapsed_seconds))
    return dict(created_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                platform=platform.platform(), processor=platform.processor(), logical_processors=os.cpu_count(),
                repeats=repeats, backend=backend, results=rows, professional=professional)


def save(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with (output / 'results.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report['results'][0]))
        writer.writeheader()
        writer.writerows(report['results'])
    groups = {}
    for row in report['results']:
        groups.setdefault((row['scenario'], row['algorithm'], row['workers']), []).append(row)
    lines = ['# LAB 3 — фактический анализ', '', '## Цель', '',
             'Сравнить цену проверки хэша, сложность пространства кандидатов и влияние воркеров.', '',
             '## Методика', '',
             'perf_counter; прогрев verifier вне замера; одинаковые кандидаты для четырёх алгоритмов; '
             'повторы и медианы. CSV содержит каждый прогон. Генерация тестового хэша не входит в время перебора. '
             f"Режим: {report.get('backend', 'threads')}; запуск/завершение воркеров входят в замер; CLI-прогресс отключён.", '',
             '## Тестовое окружение', '',
             f"{report['created_utc']}; {report['platform']}; Python {platform.python_version()}; "
             f"CPU {report['processor']}; logical CPUs {report['logical_processors']}.", '',
             '## Параметры', '',
             'bcrypt cost=10, фиксированная учебная salt; Argon2id m=65536 KiB, t=3, p=2, salt=saltsalt. '
             'Фиксированные соли нужны только для воспроизводимости учебных векторов. '
             'L3 опубликованные easy/medium отдельно проверяются тестами; неизвестные hard plaintext не заявляются.', '',
             '## Результаты', '', '| Scenario | Algorithm | Workers | N | Attempts median | Seconds median | Attempts/s median |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for (scenario, algorithm, workers), rows in groups.items():
        lines.append(f"| {scenario} | {algorithm} | {workers} | {len(rows)} | "
                     f"{statistics.median(r['attempts'] for r in rows):.0f} | "
                     f"{statistics.median(r['elapsed_seconds'] for r in rows):.9f} | "
                     f"{statistics.median(r['attempts_per_second'] for r in rows):.2f} |")
    lines += ['', '## Сравнение типов хэша', '',
              'Сопоставляйте строки одного scenario и workers. MD5/SHA-1 проверяются дёшево; bcrypt и Argon2id '
              'намеренно увеличивают стоимость проверки. Для скорости быстрых хэшей используйте fast4/fast5: '
              '3 кандидата дают прежде всего шум таймера и запуска.', '',
              '## Влияние сложности пароля', '',
              'base → length2 → length3: 3, 9, 27 кандидатов при алфавите abc; '
              'length2 → alphabet4: 9 → 16; position_first отличается от length2 только позицией (1 вместо 9). '
              'Для фиксированной длины пространство равно A**L, для диапазона длин — сумме A**L. '
              'При ранней находке время зависит от позиции, а не только от длины. '
              'Сравнение workers=1/2 использует реальные попытки: потоки могут закончить уже начатые проверки.', '',
              '## Сравнение с hashcat', '',
              'Одинаковый полный набор кандидатов передаётся как wordlist. Внешнее время включает запуск процесса, '
              'инициализацию устройства и компиляцию kernels; оно не равно чистой GPU throughput. '
              'Нулевые/отсутствующие измерения не заменяются выдуманными числами.', '',
              '| Scenario | Algorithm | Run | Supported | Cracked | Wall seconds |',
              '| --- | --- | ---: | --- | --- | ---: |']
    for r in report['professional']:
        lines.append(f"| {r['scenario']} | {r['algorithm']} | {r['repeat']} | {r.get('supported', False)} | "
                     f"{r.get('cracked', False)} | {r.get('elapsed_seconds')} |")
    if not report['professional']:
        lines.append('Профессиональное сравнение в этом запуске не выполнялось.')
    if report['professional']:
        lines += ['', 'Медианы сравнения (собственный поиск workers=1; wall time внешнего процесса):', '',
                  '| Algorithm | Own seconds | Hashcat seconds | Hashcat / own |',
                  '| --- | ---: | ---: | ---: |']
        for algorithm in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            own = [r['elapsed_seconds'] for r in report.get('professional_own', report['results'])
                   if r['scenario'] == 'base' and r['algorithm'] == algorithm and r['workers'] == 1]
            external = [r['elapsed_seconds'] for r in report['professional']
                        if r['scenario'] == 'base' and r['algorithm'] == algorithm and r.get('cracked')]
            if own and external:
                a, b = statistics.median(own), statistics.median(external)
                lines.append(f'| {algorithm} | {a:.9f} | {b:.6f} | {b/a:.2f} |')
        lines += ['', 'На трёх кандидатах запуск hashcat дороже самого поиска: это накладные расходы '
                  'инициализации/компиляции, а не доказательство превосходства Python над GPU. '
                  'Первый холодный и последующие прогоны сохранены отдельно.']
    lines += ['', '## Ограничения эксперимента', '',
              'Это ограниченный CPU/Python эксперимент, не оценка стойкости реальных учётных записей. '
              'Windows power policy, фоновые процессы, GIL и KDF internal threads влияют на результат. '
              'Большие неизвестные hard/very-hard хэши не взламывались. '
              'Из микросценария нельзя выводить пиковую скорость hashcat. Сравниваются wall times конкретного набора.', '',
              '## Вывод', '',
              'Увеличение алфавита/длины растит число проверок, а KDF увеличивает цену каждой проверки. '
              'Вывод об ускорении потоками делайте по медианам одного scenario: overhead может перевесить параллелизм.', '']
    (output / 'analysis.md').write_text('\n'.join(lines), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--hashcat', action='store_true')
    parser.add_argument('--hashcat-path', default='hashcat')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--backend', choices=('threads', 'processes'), default='threads')
    parser.add_argument('--workers', nargs='+', type=int, help='Числа воркеров для сравнения, например 1 2 4')
    parser.add_argument('--output', type=Path, default=Path('benchmarks'))
    args = parser.parse_args(argv)
    try:
        report = run(args.repeats, args.hashcat, args.hashcat_path, args.smoke, args.backend, args.workers)
        save(report, args.output)
        print(f'Saved {len(report["results"])} measurements to {args.output}')
        return 0
    except KeyboardInterrupt:
        print('Benchmark cancelled', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Небольшие CPU-эксперименты для отчёта; hashcat запускается отдельно."""
import argparse
import csv
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab3.src.cpu import crack
from lab3.src.hashes import HashTarget
from lab3.src.models import CrackConfig


def make_target(algorithm, password):
    raw = password.encode('utf-8')
    if algorithm in ('md5', 'sha1'):
        return HashTarget.parse(hashlib.new(algorithm, raw, usedforsecurity=False).hexdigest())
    if algorithm == 'bcrypt':
        import bcrypt
        return HashTarget.parse(bcrypt.hashpw(raw, b'$2b$10$abcdefghijklmnopqrstuu').decode())
    from argon2.low_level import hash_secret, Type
    return HashTarget.parse(hash_secret(raw, b'saltsalt', 3, 65536, 2, 32, Type.ID).decode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/cpu-results.csv')
    options = parser.parse_args()
    rows = []
    # One changed parameter at a time: length, alphabet, then worker count.
    for alphabet, length, workers in (('ab', 1, 1), ('ab', 2, 1), ('ab', 3, 1), ('abc', 2, 1), ('ab', 3, 2)):
        password = alphabet[-1] * length
        for algorithm in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            target = make_target(algorithm, password)
            target.matches(password)  # Import/warm-up outside timing.
            for repeat in range(1, 4):
                result = crack(target, CrackConfig(alphabet, length, length, workers))
                if result.password != password:
                    raise RuntimeError('Контрольный пароль не найден')
                rows.append(dict(algorithm=algorithm, alphabet=alphabet, length=length, workers=workers,
                                 repeat=repeat, candidates=result.candidates_checked, seconds=result.elapsed_seconds))
            print(f'{algorithm}: alphabet={alphabet}, length={length}, workers={workers}', flush=True)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with options.output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()

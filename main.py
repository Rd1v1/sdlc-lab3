"""Simple interactive entry point; command-line arguments remain available."""
import sys

from lab3.src.bruteforce import run


def ask(label, default):
    return input(f'{label} [{default}]: ').strip() or default


def main():
    if len(sys.argv) > 1:
        return run(sys.argv[1:])
    try:
        print('Моё приложение — поиск учебного пароля')
        print('Пример по умолчанию: пароль 123456, известный префикс 12345.')
        target = ask('Хэш', 'e10adc3949ba59abbe56e057f20f883e')
        backend = ask('Режим: gpu / threads / processes', 'gpu')
        source = ask('Источник: 1 — перебор, 2 — словарь', '1')
        options = [target, '--backend', backend, '--progress']
        if source == '1':
            alphabet = ask('Алфавит', '0123456789')
            prefix = ask('Известный префикс; - означает без префикса', '12345')
            options += ['--alphabet', alphabet, '--prefix', '' if prefix == '-' else prefix,
                        '--min-length', ask('Минимальная длина перебираемой части', '1'),
                        '--max-length', ask('Максимальная длина перебираемой части', '1')]
        elif source == '2':
            options += ['--wordlist', ask('Файл словаря', '.tools/wordlists/rockyou.txt')]
        else:
            print('Источник должен быть 1 или 2', file=sys.stderr)
            return 2
        if backend == 'gpu':
            options += ['--gpu-batch-size', ask('Кандидатов в GPU-пакете', '16')]
        elif source == '1':
            options += ['--workers', ask('Число воркеров', '1')]
        return run(options)
    except (KeyboardInterrupt, EOFError):
        print('\nПеребор прерван', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

# LAB 3 — запуск

Windows, PowerShell, Python 3.13+ и видеокарта с OpenCL-драйвером. Docker не нужен.

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1
```

Первый запуск устанавливает зависимости в `.venv`. Затем приложение спрашивает хэш, режим, источник кандидатов и параметры поиска. Для примера `123456` нажимайте Enter: перебираются 10 вариантов с префиксом `12345`. Для своего полного перебора укажите `-` вместо префикса и нужные длины; предел — 2 млн вариантов.

Режимы: `gpu` — хеширование на видеокарте; `threads` / `processes` — выбор числа потоков / процессов на CPU. В GPU-режиме задаётся размер пакета кандидатов. Таблица показывает наблюдаемые кандидаты воркеров, итог выводится в JSON; Ctrl+C останавливает поиск. Быстрые промежуточные кандидаты могут не попасть на экран.

Словарь RockYou загружается один раз:

```powershell
.venv/Scripts/python.exe scripts/setup-wordlist.py
```

После этого выберите источник `2` в приложении. Файл остаётся в `.tools/wordlists` и не попадает в Git. CPU-поиск по словарю использует один поток.

Для запуска без вопросов можно передавать параметры:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend processes --workers 2 --progress
powershell -ExecutionPolicy Bypass -File run.ps1 --help
```

Первый пример находит `abc`. Поддерживаются MD5, SHA-1, bcrypt и Argon2id. GPU: максимум 256 байт на кандидат, bcrypt — 72; Argon2id — 32-байтовый digest. GPU не заменяется CPU при ошибке. Криптографические OpenCL-примитивы взяты из hashcat под [MIT](lab3/src/kernels/vendor/LICENSE.txt); генерация кандидатов и управление GPU реализованы в приложении, без запуска hashcat.

Готовая сравнительная таблица и условия прежних замеров — в [REPORT.md](REPORT.md). Приложение запускает только собственный поиск. Для анализа длины, алфавита и числа CPU-воркеров:

```powershell
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --backend threads --workers 1 2 --output artifacts/threads
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --backend processes --workers 1 2 --output artifacts/processes
```

Проверка всех функций, включая реальную GPU:

```powershell
$env:LAB3_GPU_TESTS = '1'
.venv/Scripts/python.exe scripts/test.py
```

Без этой переменной GPU-тесты пропускаются. На Windows дополнительно пропускается тест POSIX-сигнала.

Код удобнее читать начиная с `main.py`, затем `lab3/src/cli.py`. Модули в `lab3/src`:

| Модуль | Назначение |
| --- | --- |
| `cli.py` | Аргументы, выбор режима и вывод результата |
| `models.py` | Параметры поиска, результат, состояние воркеров |
| `hashes.py` | Разбор хэшей и проверка пароля |
| `candidates.py` | Генерация паролей по алфавиту и длине |
| `cpu.py` | Поиск с потоками или процессами |
| `gpu.py` | OpenCL-вычисления и поиск на GPU |
| `wordlist.py` | Чтение словаря и CPU-поиск по нему |
| `progress.py` | Таблица кандидатов CPU-воркеров |
| `benchmark.py` | Замеры длины, алфавита и числа CPU-воркеров |
| `bruteforce.py` | Совместимость с прежними импортами и командой запуска |

Hashcat запускается отдельно. Скачайте архив с [официального сайта](https://hashcat.net/hashcat/) и распакуйте его так, чтобы файл находился в `.tools/hashcat/hashcat-7.1.2/hashcat.exe`. Установка hashcat не нужна для работы моего приложения.

Пример отдельного GPU-поиска MD5 пароля `123456`, без словаря и с тем же RockYou:

```powershell
$wordlist = (Resolve-Path .tools/wordlists/rockyou.txt).Path
Push-Location .tools/hashcat/hashcat-7.1.2
./hashcat.exe --backend-ignore-cuda --backend-ignore-hip -D 2 -d 1 --potfile-disable --restore-disable --logfile-disable -m 0 -a 3 --markov-disable e10adc3949ba59abbe56e057f20f883e '12345?d'
./hashcat.exe --backend-ignore-cuda --backend-ignore-hip -D 2 -d 1 --potfile-disable --restore-disable --logfile-disable --wordlist-autohex-disable -m 0 -a 0 e10adc3949ba59abbe56e057f20f883e $wordlist
Pop-Location
```

Для других хэшей замените значение хэша и `-m`: MD5 — `0`, SHA-1 — `100`, bcrypt — `3200`, Argon2id — `34000`. Учебные хэши находятся в [assignment-hashes.json](lab3/examples/assignment-hashes.json). Для сравнения запустите моё приложение с `--backend gpu --no-progress` на том же хэше и наборе кандидатов. Для полного времени запуска используйте `Measure-Command`, направив вывод команды в `Out-Host`; выполните три последовательных запуска и возьмите медиану.

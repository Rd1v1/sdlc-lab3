# LAB 3 — запуск

Команды выполняются в PowerShell из корня репозитория. Требуется Python 3.13+.

GPU-приложение и hashcat запускаются напрямую в Windows. Нужна видеокарта с работающим OpenCL-драйвером. Пакеты устанавливаются только в локальную `.venv`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m pip install --cache-dir .cache/pip -r requirements-gpu.txt
.venv/Scripts/python.exe scripts/setup-wordlist.py
.venv/Scripts/python.exe -m lab3.src.bruteforce e10adc3949ba59abbe56e057f20f883e --prefix 12345 --alphabet 0123456789 --min-length 1 --max-length 1 --backend gpu --gpu-batch-size 16 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce e10adc3949ba59abbe56e057f20f883e --wordlist .tools/wordlists/rockyou.txt --backend gpu --gpu-batch-size 16 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend threads --workers 2 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend processes --workers 2 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --interactive --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce --help
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --backend threads --workers 1 2 --output artifacts/smoke-threads
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --backend processes --workers 1 2 --output artifacts/smoke-processes
.venv/Scripts/python.exe scripts/test.py
```

Полная проверка с реальными GPU-тестами:

```powershell
$env:LAB3_GPU_TESTS = '1'
.venv/Scripts/python.exe scripts/test.py
```

Без этой переменной GPU-тесты пропускаются, чтобы CPU-режимы можно было проверять без видеокарты и PyOpenCL.

Пример с хэшем `4a8a08...` находит `c`, примеры с хэшем `900150...` — `abc`. `--interactive` запрашивает режим и число воркеров. `--workers N` задаёт число потоков (`threads`) или процессов (`processes`); предел — число логических CPU, максимум 64 (для процессов Windows — 61).

Примеры с хэшем `e10adc...` находят `123456`: в первом генерируются 10 вариантов с известным префиксом `12345`, во втором используется полный `rockyou.txt`. GPU-режим читает исходные байты по порядку и отправляет пакеты кандидатов на видеокарту; CPU-режим словаря использует один поток; `--alphabet` и длины в нём не фильтруют словарь. Скрипт загрузки сохраняет файл в `.tools/wordlists` и проверяет SHA-256 при повторном запуске. `--prefix` применяется только к генерируемым кандидатам; длины относятся к части после префикса.

В терминале таблица воркеров включена автоматически; `--progress` включает её явно, `--no-progress` отключает. Строка показывает состояние, число завершённых проверок и последний наблюдаемый кандидат. Экран обновляется примерно каждые 0,1 с: быстрые промежуточные кандидаты пропускаются. `found` означает находку, `done` — исчерпанный диапазон, `stopped` — остановку после находки другим воркером. Для короткого поиска видна преимущественно итоговая таблица.

Таблица выводится в stderr, JSON-результат — в stdout. Ctrl+C останавливает перебор после завершения уже начатых проверок. При перенаправлении вывода таблица по умолчанию отключается; с `--progress` сохраняются текстовые снимки без управляющих последовательностей.

Полные замеры с тремя повторами (визуализация отключена; время включает запуск и завершение воркеров):

```powershell
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --backend threads --workers 1 2 --output artifacts/full-threads
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --backend processes --workers 1 2 --output artifacts/full-processes
```

CSV/JSON и анализ создаются в указанном каталоге `artifacts`. Для установки portable hashcat выполните `powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1`. Для GPU-сравнения используйте следующий скрипт. При отсутствии подходящего устройства результат отмечается как недоступный.

Сводная таблица фактических скоростей находится в [REPORT.md](REPORT.md). Повторить сравнение на GPU:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/benchmark-gpu.ps1 -Repeats 3
```

Оба приложения хешируют на одной RTX 4070 SUPER через OpenCL и запускаются последовательно. Для каждого замера запускается отдельный процесс; время включает подготовку GPU и поиск. Без словаря используется маска `12345?d`, со словарём — полный RockYou с тем же учебным паролем. Результаты сохраняются в `artifacts/gpu-summary`.

`--backend gpu` включает GPU-бэкенд вашего приложения; `--gpu-batch-size 16` задаёт число кандидатов в пакете. `--gpu-device 0` выбирает первую GPU OpenCL. В выводе `--progress` видны кандидаты текущего GPU-пакета; `--workers` относится к CPU-режимам. Для Argon2id с 64 МиБ памяти допустимо до 32 кандидатов в пакете. При нехватке памяти уменьшите пакет. GPU автоматически не заменяется CPU.

Ограничения GPU-бэкенда: до 256 байт на кандидата (bcrypt — до 72), Argon2id с 32-байтовым digest. Неподдерживаемые длины кандидатов в словаре учитываются в `rejected`. Существующие CPU-режимы `threads` и `processes` сохранены для лабораторных сравнений.

OpenCL-криптографические примитивы заимствованы из hashcat 7.1.2 под MIT; [лицензия](lab3/src/kernels/vendor/LICENSE.txt) и [происхождение](lab3/src/kernels/vendor/ORIGIN.json) сохранены. Приложение самостоятельно генерирует кандидатов, читает словарь, передаёт данные на GPU и запускает OpenCL-ядра через PyOpenCL. Исполняемый файл hashcat не используется для поиска вашего приложения.

# LAB 3 — запуск

Команды выполняются в PowerShell из корня репозитория. Требуется Python 3.13+.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m lab3.src.bruteforce 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend threads --workers 2 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend processes --workers 2 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --interactive --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce --help
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --backend threads --workers 1 2 --output artifacts/smoke-threads
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --backend processes --workers 1 2 --output artifacts/smoke-processes
.venv/Scripts/python.exe scripts/test.py
```

Первый пример находит `c`, примеры с воркерами — `abc`. `--interactive` запрашивает режим и число воркеров. `--workers N` задаёт число потоков (`threads`) или процессов (`processes`); предел — число логических CPU, максимум 64 (для процессов Windows — 61).

В терминале таблица воркеров включена автоматически; `--progress` включает её явно, `--no-progress` отключает. Строка показывает состояние, число завершённых проверок и последний наблюдаемый кандидат. Экран обновляется примерно каждые 0,1 с: быстрые промежуточные кандидаты пропускаются. `found` означает находку, `done` — исчерпанный диапазон, `stopped` — остановку после находки другим воркером. Для короткого поиска видна преимущественно итоговая таблица.

Таблица выводится в stderr, JSON-результат — в stdout. Ctrl+C останавливает перебор после завершения уже начатых проверок. При перенаправлении вывода таблица по умолчанию отключается; с `--progress` сохраняются текстовые снимки без управляющих последовательностей.

Полные замеры с тремя повторами (визуализация отключена; время включает запуск и завершение воркеров):

```powershell
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --backend threads --workers 1 2 --output artifacts/full-threads
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --backend processes --workers 1 2 --output artifacts/full-processes
```

CSV/JSON и анализ создаются в указанном каталоге `artifacts`. Для установки portable hashcat выполните `powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1`. Для CPU-сравнения используйте следующий скрипт. При отсутствии подходящего устройства результат отмечается как недоступный.

Сводная таблица фактических скоростей находится в [REPORT.md](REPORT.md). Повторить CPU-сравнение с тремя замерами (нужен Docker Desktop с Linux engine):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/benchmark-cpu.ps1 -Repeats 3
```

Оба инструмента запускаются в одном контейнере, ограниченном одним логическим CPU. Hashcat использует CPU OpenCL (PoCL), параметры `-D 1 --backend-ignore-cuda --backend-ignore-hip`. Python-пакеты и PoCL устанавливаются внутри контейнера; результаты сохраняются в `artifacts/cpu-summary`.

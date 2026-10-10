# LAB 3 — запуск

Команды выполняются в PowerShell из корня репозитория. Требуется Python 3.13+.

Для самого приложения и тестов Docker не нужен. По сохранённым требованиям LAB 3 он не обязателен; актуальная страница задания сейчас недоступна. Docker используется здесь как дополнительный стенд CPU OpenCL для hashcat.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe scripts/setup-wordlist.py
.venv/Scripts/python.exe -m lab3.src.bruteforce e10adc3949ba59abbe56e057f20f883e --prefix 12345 --alphabet 0123456789 --min-length 1 --max-length 1 --workers 1 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce e10adc3949ba59abbe56e057f20f883e --wordlist .tools/wordlists/rockyou.txt --workers 1 --backend threads --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend threads --workers 2 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --backend processes --workers 2 --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce 900150983cd24fb0d6963f7d28e17f72 --alphabet abc --min-length 3 --max-length 3 --interactive --progress
.venv/Scripts/python.exe -m lab3.src.bruteforce --help
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --backend threads --workers 1 2 --output artifacts/smoke-threads
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --backend processes --workers 1 2 --output artifacts/smoke-processes
.venv/Scripts/python.exe scripts/test.py
```

Пример с хэшем `4a8a08...` находит `c`, примеры с хэшем `900150...` — `abc`. `--interactive` запрашивает режим и число воркеров. `--workers N` задаёт число потоков (`threads`) или процессов (`processes`); предел — число логических CPU, максимум 64 (для процессов Windows — 61).

Примеры с хэшем `e10adc...` находят `123456`: в первом генерируются 10 вариантов с известным префиксом `12345`, во втором используется полный `rockyou.txt`. Словарный режим читает исходные байты по порядку в одном потоке; `--alphabet` и длины в нём не фильтруют словарь. Скрипт загрузки сохраняет файл в `.tools/wordlists` и проверяет SHA-256 при повторном запуске. `--prefix` применяется только к генерируемым кандидатам; длины относятся к части после префикса.

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
powershell -ExecutionPolicy Bypass -File scripts/benchmark-cpu.ps1 -Repeats 3 -Comparison dictionary
```

Оба инструмента запускаются в одном контейнере, ограниченном одним логическим CPU. Hashcat использует CPU OpenCL (PoCL), параметры `-D 1 --backend-ignore-cuda --backend-ignore-hip`: без словаря — маска `-a 3`, с RockYou — словарный режим `-a 0`. Python-пакеты и PoCL устанавливаются внутри контейнера; результаты сохраняются в `artifacts/cpu-summary`. Сравнение ограничено учебной маской `12345?d` и тем же паролем в словаре; это не полный перебор всех шестизначных паролей.

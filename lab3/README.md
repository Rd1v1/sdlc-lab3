# LAB 3 — Offline password search

## Стек

Python3.13+, hashlib/argparse/dataclasses/time и ThreadPoolExecutor. Для bcrypt
и Argon2id: bcrypt4.3.0, argon2-cffi25.1.0 с pinned-зависимостями requirements.txt.
Пакеты устанавливаются только в проектную .venv. Опционально — portable hashcat7.1.2
в .tools и уже установленный compute driver. Проект не устанавливает драйверы.

## Инструкция

Из корня репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m lab3.src.bruteforce 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1
.venv/Scripts/python.exe scripts/test.py --lab 3
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --output artifacts/lab3-smoke
```

Hash примера — MD5 учебного c: found=true, password=c, три проверки. С alphabet=ab
пароль отсутствует и код выхода1. Ошибка параметров —2, Ctrl+C —130, найдено —0.
Linux: `sh scripts/setup.sh`, затем `.venv/bin/python` с теми же аргументами.

Повтор эксперимента с сохранением прежних benchmarks:

```powershell
.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3 --output artifacts/lab3-experiment
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --hashcat --hashcat-path .tools/hashcat/hashcat-7.1.2/hashcat.exe --output artifacts/lab3-professional
```

JSON, CSV и analysis.md появятся в output. Отдельный путь предотвращает
перезапись включённых в репозиторий исторических измерений.

## Как устроен код

`HashTarget.parse` распознаёт длину MD5/SHA1 и формат bcrypt/Argon2id. Проверяет
base64, salt/digest lengths и учебные KDF-лимиты. `matches` считает быстрый hash
либо вызывает проверяющий API KDF. usedforsecurity=False у MD5/SHA1 означает
изучаемые hash-данные, а не хранение паролей приложения.

`CrackConfig.validate` ограничивает алфавит (1–128 уникальных символов), длину1–8,
число кандидатов (по умолчанию2млн) и потоков (до64, не больше CPU).
`candidate_at` переводит индекс в систему счисления по размеру алфавита;
`iter_candidates` перебирает длины и индексы без хранения всего пространства.
Для диапазона длин число кандидатов равно сумме A^L.

`crack` в одном потоке останавливается на совпадении. В нескольких — делит
пространство на непересекающиеся chunks и использует ThreadPoolExecutor.
Event прекращает новые проверки, pending futures отменяются. Счётчик складывает
реальные попытки задач; он может превышать последовательную позицию пароля.
finally выставляет Event также при отмене/ошибке.

`benchmark.make_target` создаёт воспроизводимые учебные цели; `run` прогревает
verifier вне времени, измеряет perf_counter, повторяет сценарии hash type,
длины, алфавита, позиции и workers. `save` сохраняет каждый прогон, медианы
и текстовый отчёт. Генерация цели не включена в search time.

`compare_hashcat` создаёт временный wordlist из тех же кандидатов, отключает
potfile/restore/log, запускает бинарник и проверяет найденное значение своим
verifier. Время включает startup/инициализацию GPU; это не пиковая throughput.
Недоступность инструмента записывается unavailable, а не нулевой скоростью.

## Проверки и ограничения

Тесты: векторы, published easy/medium, exhaustion, счётчики, полное покрытие без
дублей, malformed hash, границы и CLI cancellation. Новый повтор и professional
smoke: [аудит](../docs/audit-2026-10-10.md). Неизвестные hard/very-hard не заявлены
найденными. GIL, KDF threads и startup overhead не позволяют экстраполировать
микроэксперимент на большие GPU-задачи. Поиск только offline по собственным хэшам.

## Исторические результаты

Код перенесён из старой папки lab2 с сохранением реализации. Актуальная LAB 2 теперь CI/CD.

Запуск из корня: `./scripts/setup.ps1`, затем `./scripts/run_lab3.ps1 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1`.

Алгоритмы: MD5, SHA-1, bcrypt и Argon2id. Собственная генерация/поиск, опциональные threads, лимиты параметров, понятные exit codes. Сетевых атак нет.

Benchmark: `.venv/Scripts/python.exe -m lab3.src.benchmark --repeats 3`.
Профессиональное сравнение: добавить `--hashcat --hashcat-path .tools/hashcat/hashcat-7.1.2/hashcat.exe --output benchmarks/with-hashcat`.

Текущие результаты: [анализ](../docs/lab3-analysis.md), [CSV](../benchmarks/results.csv), [JSON включая hashcat](../benchmarks/results.json). [Защита](../docs/lab3-defense.md).

`examples/assignment-hashes.json` содержит опубликованные в актуальной LAB 3 хэши; easy/medium значения подтверждены, неизвестные hard/very-hard пароли не заявлены найденными. `examples/benchmark-results.json` — исторический короткий замер, не текущий итоговый эксперимент.

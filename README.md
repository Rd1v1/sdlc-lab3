# LAB 3 — самостоятельный репозиторий

## Стек

Python3.13+, hashlib/argparse/dataclasses/time и ThreadPoolExecutor. Для bcrypt
и Argon2id: bcrypt4.3.0, argon2-cffi25.1.0 с pinned-зависимостями requirements.txt.
Пакеты устанавливаются только в проектную .venv. Опционально — portable hashcat7.1.2
в .tools и уже установленный compute driver. Проект не устанавливает драйверы.

## Запуск

Все команды из корня этого репозитория. Python3.13+, Docker Desktop/Linux engine там, где вызывается Docker. Проектные зависимости не устанавливаются глобально.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe -m lab3.src.bruteforce 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --output artifacts/smoke
```



## Объяснение кода

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

## Материалы и ограничения

- [lab3-defense.md](docs/lab3-defense.md)
- [lab3-analysis.md](docs/lab3-analysis.md)

Исходный README лабораторной: [lab3/README.md](lab3/README.md). Он сохранён как историческая документация монорепозитория; актуальные самостоятельные команды приведены выше. Evidence относится к исходному аудиту 10.10.2026 и не выдаётся за новый запуск этого репозитория. Свежая проверка разделения — VALIDATION.md.

Уязвимые упражнения/сканеры используются только в собственном loopback-стенде. Не запускать несколько копий Docker-стенда одновременно: порты и имена сервисов фиксированы.

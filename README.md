# LAB 3 — запуск

Windows, PowerShell, Python 3.13+. Для режима GPU нужен OpenCL-драйвер видеокарты. Docker не требуется. Команды выполняются из корня репозитория.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe main.py
```

Зависимости устанавливаются в `.venv`. Приложение запросит хэш, режим (`gpu`, `threads`, `processes`), параметры перебора и число воркеров. Enter выбирает значения по умолчанию: поиск пароля `123456` среди десяти вариантов с префиксом `12345` на GPU. Для перебора без префикса введите `-` в соответствующем вопросе.

Запуск с четырьмя GPU-воркерами без вопросов:

```powershell
.venv/Scripts/python.exe main.py e10adc3949ba59abbe56e057f20f883e --backend gpu --workers 4 --alphabet 0123456789 --prefix 12345 --min-length 1 --max-length 1 --progress
```

`--workers` задаёт число потоков/процессов CPU или параллельных кандидатов в GPU-пакете. CLI показывает состояние, текущий кандидат, число проверок и найденный пароль каждого воркера. Ctrl+C останавливает поиск. Все параметры: `.venv/Scripts/python.exe main.py --help`.

Поиск с RockYou:

```powershell
.venv/Scripts/python.exe scripts/setup-wordlist.py
.venv/Scripts/python.exe main.py e10adc3949ba59abbe56e057f20f883e --backend gpu --workers 4 --wordlist .tools/wordlists/rockyou.txt --progress
```

## Сравнение с hashcat

Оба приложения используют GPU. Указана медиана трёх запусков: полное время процесса в секундах, включая подготовку GPU.

| Алгоритм | Режим | Моё приложение, с | hashcat, с |
| --- | --- | ---: | ---: |
| MD5 | Без словаря | 0.764 | 2.404 |
| MD5 | RockYou | 1.039 | 2.725 |
| SHA-1 | Без словаря | 0.738 | 2.513 |
| SHA-1 | RockYou | 1.046 | 2.953 |
| bcrypt | Без словаря | 1.286 | 8.762 |
| bcrypt | RockYou | 1.655 | 11.357 |
| Argon2id | Без словаря | 0.911 | 5.912 |
| Argon2id | RockYou | 1.237 | 2.866 |

Без словаря: маска `12345?d`, 10 вариантов. RockYou: 14 344 391 строка, пароль `123456` находится в первой строке. Поиск прекращается после находки; это не время проверки всего словаря и не пиковая скорость хэширования.

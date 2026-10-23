# LAB 3 — запуск

Windows, PowerShell, Python 3.13+. Для `--gpu` нужен OpenCL-драйвер видеокарты. Docker не требуется. Команды выполняются из корня репозитория.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe main.py 9df62e693988eb4e1e1444ece0578579 --alphabet abc --min-length 3 --max-length 3 --workers 2
```

Пример находит `ccc`. По умолчанию используется CPU: `--workers 1` — последовательный поиск, больше одного — потоки. CLI показывает текущий кандидат, число проверок и найденный пароль каждого воркера. Все параметры: `.venv/Scripts/python.exe main.py --help`.

Для GPU добавьте ключ `--gpu`; число воркеров означает число параллельных кандидатов в пакете:

```powershell
.venv/Scripts/python.exe main.py 9df62e693988eb4e1e1444ece0578579 --alphabet abc --min-length 3 --max-length 3 --gpu --workers 16
```

Поиск с RockYou (без `--gpu` та же команда работает на CPU):

```powershell
.venv/Scripts/python.exe scripts/setup-wordlist.py
.venv/Scripts/python.exe main.py e10adc3949ba59abbe56e057f20f883e --wordlist .tools/wordlists/rockyou.txt --gpu --workers 16
```

Ctrl+C останавливает поиск. `--no-progress` отключает таблицу для замеров. Параметры передаются командой, вопросов при запуске нет.

## Сравнение с hashcat

| Алгоритм | Режим | Моё приложение, с | hashcat, с |
| --- | --- | ---: | ---: |
| MD5 | Без словаря | 0.792 | 2.063 |
| MD5 | RockYou | 0.830 | 1.495 |
| SHA-1 | Без словаря | 0.606 | 1.899 |
| SHA-1 | RockYou | 0.581 | 1.458 |
| bcrypt | Без словаря | 1.463 | 7.893 |
| bcrypt | RockYou | 1.015 | 10.859 |
| Argon2id | Без словаря | 0.907 | 2.729 |
| Argon2id | RockYou | 0.761 | 2.386 |

Оба приложения используют одну GPU. Указана медиана трёх запусков: полное время отдельного процесса в секундах, включая подготовку GPU.

Без словаря: алфавит `abc`, длина 3, пароль `ccc`, 27 вариантов. RockYou: 14 344 391 строка, пароль `123456` находится в первой строке. Поиск прекращается после находки; это не время проверки всего словаря и не пиковая скорость хэширования.

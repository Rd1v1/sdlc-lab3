# LAB 3 — запуск

Windows, PowerShell, Python 3.13+. Для `--gpu` нужен OpenCL-драйвер видеокарты. Команды выполняются из корня репозитория.

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

Ctrl+C останавливает поиск. `--no-progress` отключает таблицу для замеров.

## Хэши для запуска

Можно передать собственный хэш MD5, SHA-1, bcrypt или Argon2id. Тип определяется автоматически по формату строки. Для нахождения пароля он должен входить в выбранный алфавит и диапазон длин либо присутствовать в словаре.

Ограничения приложения: параметр сложности bcrypt (`cost`) — 4–12; Argon2id — версия 19, память до 256 МиБ, 1–10 проходов и 1–8 линий параллелизма. На GPU длина результата хэширования Argon2id должна быть 32 байта. При переборе без словаря допускается до 2 млн кандидатов.

В PowerShell передавайте хэш в одинарных кавычках, чтобы символы `$` сохранились:

```powershell
.venv/Scripts/python.exe main.py '$2a$10$z4u9ZkvopUiiytaNX7wfGedy9Lu2ywUxwYpbsAR5YBrAuUs3YGXdi' --wordlist .tools/wordlists/rockyou.txt --workers 2
```

### MD5

easy:

```text
e10adc3949ba59abbe56e057f20f883e
```

medium:

```text
1f3870be274f6c49b3e31a0c6728957f
```

hard:

```text
77892341aa9dc66e97f5c248782b5d92
```

very_hard:

```text
686e697538050e4664636337cc3b834f
```

### SHA-1

easy:

```text
7c4a8d09ca3762af61e59520943dc26494f8941b
```

medium:

```text
d0be2dc421be4fcd0172e5afceea3970e2f3d940
```

hard:

```text
666846867fc5e0a46a7afc53eb8060967862f333
```

very_hard:

```text
6e157c5da4410b7e9de85f5c93026b9176e69064
```

### bcrypt

easy:

```text
$2a$10$z4u9ZkvopUiiytaNX7wfGedy9Lu2ywUxwYpbsAR5YBrAuUs3YGXdi
```

medium:

```text
$2a$10$26GB/T2/6aTsMkTjCgqm/.JP8SUjr32Bhfn9m9smtDiIwM4QIt2ze
```

hard:

```text
$2a$10$Q9M0vLLrE4/nu/9JEMXFTewB3Yr9uMdIEZ1Sgdk1NQTjHwLN0asfi
```

very_hard:

```text
$2a$10$yZBadi8Szw0nItV2g96P6eqctI2kbG/.mb0uD/ID9tlof0zpJLLL2
```

### Argon2id

easy:

```text
$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$PUF5UxxoUY++mMekkQwFurL0ZsTtB7lelO23zcyZQ0c
```

medium:

```text
$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$HYQwRUw9VcfkvqkUQ5ppyYPom6f/ro3ZCXYznhrYZw4
```

hard:

```text
$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$9asGA7Xv3vQBz7Yyh4/Ntw0GQgOg8R6OWolOfRETrEg
```

very_hard:

```text
$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHQ$+smq45/czydGj0lYNdZVXF++FOXJwrkXt6VUIcEauvo
```

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

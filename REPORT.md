# Сравнение с hashcat

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


## Условия измерений

bcrypt: cost=10. Argon2id: m=65536 КиБ, t=3, p=2. Для каждого алгоритма и режима использованы одинаковые целевые хэши и наборы кандидатов. GPU-запуски выполнялись последовательно, с сохранённым кэшем компиляции и отключённой таблицей прогресса. Все запуски завершились нахождением контрольного пароля.

## Запуск hashcat

Распакуйте [hashcat](https://hashcat.net/hashcat/) в `.tools/hashcat/hashcat-7.1.2`. Команды выполняются из корня репозитория после подготовки RockYou по README.

```powershell
$wordlist = (Resolve-Path .tools/wordlists/rockyou.txt).Path
Push-Location .tools/hashcat/hashcat-7.1.2
./hashcat.exe --quiet --backend-ignore-cuda --backend-ignore-hip -D 2 -d 1 --potfile-disable --restore-disable --logfile-disable -m 0 -a 3 -1 abc --markov-disable 9df62e693988eb4e1e1444ece0578579 '?1?1?1'
./hashcat.exe --quiet --backend-ignore-cuda --backend-ignore-hip -D 2 -d 1 --potfile-disable --restore-disable --logfile-disable --wordlist-autohex-disable -m 0 -a 0 e10adc3949ba59abbe56e057f20f883e $wordlist
Pop-Location
```

Первый пример находит `ccc`, второй — `123456`. Режимы `-m`: MD5 — `0`, SHA-1 — `100`, bcrypt — `3200`, Argon2id — `34000`. Для другого алгоритма укажите соответствующий хэш.

Моё приложение запускается командами из [README.md](README.md) с параметрами `--gpu --workers 16 --no-progress`. Hashcat запускается отдельно. Для повторения сравнения измерьте полное время каждой команды через `Measure-Command`, направив её вывод в `Out-Host`; выполните три запуска и возьмите медиану. Исходные значения сохранены в `reports/comparison-results.csv` и `reports/comparison-results.json`.

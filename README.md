# LAB 3 — запуск

Команды выполняются в PowerShell из корня репозитория. Требуется Python 3.13+.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe -m lab3.src.bruteforce 4a8a08f09d37b73795649038408b5f33 --alphabet abc --min-length 1 --max-length 1
.venv/Scripts/python.exe -m lab3.src.bruteforce --help
.venv/Scripts/python.exe -m lab3.src.benchmark --smoke --repeats 1 --output artifacts/smoke
.venv/Scripts/python.exe scripts/test.py
```

Пример перебирает локальный учебный MD5; найденный пароль — `c`. Результаты замеров сохраняются в `artifacts/smoke`.

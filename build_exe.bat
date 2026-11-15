@echo off
rem ---------------------------------------------------------------
rem  Сборка PhoneCleaner.exe одним файлом
rem  Требуется Python 3.10+ (python в PATH)
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/4] Создаю виртуальное окружение...
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat

echo [2/4] Ставлю зависимости...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :error

if not exist "phone_cleaner\assets\icon.ico" (
    echo [3/4] Рисую иконку...
    python scripts\make_icon.py || goto :error
)

echo [4/4] Собираю exe...
pyinstaller --noconfirm --clean PhoneCleaner.spec || goto :error

echo.
echo Готово: dist\PhoneCleaner.exe
pause
exit /b 0

:error
echo.
echo Сборка не удалась. Смотрите сообщения выше.
pause
exit /b 1

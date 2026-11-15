#!/usr/bin/env bash
# Сборка исполняемого файла для текущей ОС (Linux/macOS/Windows с bash).
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then "$PY" -m venv .venv; fi
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt pyinstaller

if [ ! -f phone_cleaner/assets/icon.ico ]; then
  python scripts/make_icon.py || true
fi

python -m pytest tests -q
pyinstaller --noconfirm --clean PhoneCleaner.spec
echo "Готово: dist/PhoneCleaner"

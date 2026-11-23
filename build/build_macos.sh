#!/usr/bin/env bash
# Сборка приложения macOS (.app + .dmg). Этот сценарий ещё не проверялся на Mac.
set -euo pipefail

cd "$(dirname "$0")/.."   # корень репозитория

echo "==> PyInstaller: сборка backend"
python -m PyInstaller --noconfirm --clean --workpath .pyi-build packaging/backend.spec

resources="app/src-tauri/resources/backend"
rm -rf "$resources"
mkdir -p "$resources"
cp -R dist/mpv-cinema-backend/. "$resources"

echo "==> Tauri: сборка приложения"
(
  cd app
  npm install --no-fund --no-audit
  npx tauri build --bundles app,dmg --config src-tauri/tauri.bundle.json
)

echo "✅ Готово: app/src-tauri/target/release/bundle"
echo "Нужен установленный mpv (brew install mpv). Сам mpv в приложение не входит."

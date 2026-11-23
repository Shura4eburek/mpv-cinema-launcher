# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: backend приложения (onedir, Windows и macOS).
# Сборка из корня репозитория: python -m PyInstaller --noconfirm packaging/backend.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Selenium Manager сам находит chromedriver; файлы других платформ в сборке не нужны.
other_platforms = {
    "win32": ("linux-arm64", "linux-x86_64", "macos"),
    "darwin": ("linux-arm64", "linux-x86_64", "windows"),
}.get(sys.platform, ())
selenium_data = [
    (source, target)
    for source, target in collect_data_files("selenium")
    if os.path.basename(target) not in other_platforms
]

# Шейдеры скачиваются при первом запуске и в сборку не входят.
datas = [
    ("../mpv-profiles/*.conf", "mpv-profiles"),
    ("../mpv-profiles/player", "mpv-profiles/player"),
    *selenium_data,
    # keyring находит хранилища через entry points из своих метаданных.
    *copy_metadata("keyring"),
]
# Идентификатор Google-клиента не хранится в git; без файла вход в сборке недоступен.
if os.path.exists(os.path.join(SPECPATH, "google_client.json")):
    datas.append(("google_client.json", "."))

# Пути относительно каталога этого .spec (packaging/).
a = Analysis(
    ["backend_entry.py"],
    pathex=[os.path.join(SPECPATH, "..", "src")],
    binaries=[],
    datas=datas,
    # selenium.webdriver загружает драйверы лениво, поэтому анализ импортов их не видит.
    hiddenimports=collect_submodules("selenium.webdriver.chrome") + collect_submodules("selenium.webdriver.chromium")
    # Модули хранилищ keyring загружаются по entry points, анализ импортов их не видит.
    + collect_submodules("keyring.backends"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "customtkinter", "PIL", "pytest", "numpy", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

# console=True нужен для настоящих stdin и stdout; окно скрывает приложение Tauri.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mpv-cinema-backend",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="mpv-cinema-backend")

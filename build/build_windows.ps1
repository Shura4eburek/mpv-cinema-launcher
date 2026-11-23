# Сборка установщика Windows. Запуск:
#   python -m pip install -e ".[build]"
#   pwsh -ExecutionPolicy Bypass -File build\build_windows.ps1
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")   # корень репозитория

# Каталог сборки Rust занимает гигабайты: не держим его в синхронизируемой папке.
if (-not $env:CARGO_TARGET_DIR) {
    $env:CARGO_TARGET_DIR = Join-Path $env:LOCALAPPDATA "mpv-cinema-target"
}

Write-Host "==> PyInstaller: сборка backend"
python -m PyInstaller --noconfirm --clean --workpath .pyi-build packaging/backend.spec
if ($LASTEXITCODE -ne 0) { throw "Сборка backend не удалась" }

$resources = "app\src-tauri\resources\backend"
if (Test-Path $resources) { Remove-Item -Recurse -Force $resources }
New-Item -ItemType Directory -Force $resources | Out-Null
Copy-Item "dist\mpv-cinema-backend\*" $resources -Recurse

Write-Host "==> Lampac: подготовка"
# Версии закреплены вместе с контрольными суммами: обновление меняет обе строки.
$lampacVersion = "1.87.6"
$lampacZip = @{ Url = "https://github.com/lampac-nextgen/lampac/releases/download/$lampacVersion/lampac-nextgen.zip"; Algo = "SHA256"; Hash = "f69f289ade75c5e3eb86b39936507bdc380314c41936bb1c2fd012e6eecbd5fe" }
$runtimeZip = @{ Url = "https://builds.dotnet.microsoft.com/dotnet/aspnetcore/Runtime/10.0.14/aspnetcore-runtime-10.0.14-win-x64.zip"; Algo = "SHA512"; Hash = "f26712cbc7a0c3de6c78c78d2ec80f5a96e3da97f3ce67e964a66bc2d8638cf02f67113c28be5431b2739b29732d918bc3210064b52c845fe914e56fcd058acb" }

function Get-Verified($item, $name) {
    $cache = Join-Path $env:CARGO_TARGET_DIR "lampac-downloads"
    New-Item -ItemType Directory -Force $cache | Out-Null
    $zip = Join-Path $cache $name
    $valid = (Test-Path $zip) -and ((Get-FileHash $zip -Algorithm $item.Algo).Hash -eq $item.Hash)
    if (-not $valid) {
        Invoke-WebRequest $item.Url -OutFile $zip
        if ((Get-FileHash $zip -Algorithm $item.Algo).Hash -ne $item.Hash) {
            Remove-Item $zip
            throw "Контрольная сумма $name не совпала"
        }
    }
    return $zip
}

$lampacOut = "app\src-tauri\resources\lampac"
if (Test-Path $lampacOut) { Remove-Item -Recurse -Force $lampacOut }
New-Item -ItemType Directory -Force $lampacOut | Out-Null
Expand-Archive (Get-Verified $lampacZip "lampac-$lampacVersion.zip") "$lampacOut\app"
Expand-Archive (Get-Verified $runtimeZip "aspnetcore-runtime-10.0.14.zip") "$lampacOut\runtime"

# Лишнее: браузер не используется, остальное относится к другим системам и службам.
Remove-Item -Recurse -Force "$lampacOut\app\.playwright"
Get-ChildItem "$lampacOut\app\runtimes" -Directory | Where-Object { $_.Name -notin "win", "win-x64", "references" } | Remove-Item -Recurse -Force
Get-ChildItem "$lampacOut\app\module" -Directory | Where-Object { $_.Name -notin "Online", "OnlineRUS", "OnlineUKR", "Proxy" } | Remove-Item -Recurse -Force
Set-Content "$lampacOut\VERSION" $lampacVersion -Encoding ascii
Copy-Item "packaging\lampac\LICENSE", "packaging\lampac\SOURCE.txt" $lampacOut

Write-Host "==> Tauri: сборка приложения"
Push-Location app
try {
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw "npm install не удался" }
    npx tauri build --config src-tauri/tauri.bundle.windows.json
    if ($LASTEXITCODE -ne 0) { throw "Сборка Tauri не удалась" }
} finally {
    Pop-Location
}

$bundle = Join-Path $env:CARGO_TARGET_DIR "release\bundle\nsis"
Write-Host "Готово: установщик в $bundle"
Write-Host "Нужен установленный mpv (winget install mpv). Сам mpv в приложение не входит."

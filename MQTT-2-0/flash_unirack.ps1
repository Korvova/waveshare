# Прошивка Unirack-1: автоопределение платы RP2350, заливка, проверка, перезагрузка.
# Запуск:  powershell -ExecutionPolicy Bypass -File flash_unirack.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. Найти COM-порт платы (Raspberry Pi VID 2E8A)
$dev = Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -match 'VID_2E8A' -and $_.FriendlyName -match 'COM\d+'
} | Select-Object -First 1
if (-not $dev) {
    Write-Host "Плата RP2350 не найдена. Проверьте USB-кабель (нужен кабель с данными)." -ForegroundColor Red
    exit 1
}
$com = [regex]::Match($dev.FriendlyName, 'COM\d+').Value
Write-Host "Плата найдена на $com" -ForegroundColor Cyan

# 2. Залить файлы (с повторами: плата может ещё грузиться после подключения)
foreach ($f in @("w5500_simple.py", "main.py")) {
    $done = $false
    foreach ($try in 1..4) {
        mpremote connect $com cp $f ":$f"
        if ($LASTEXITCODE -eq 0) { $done = $true; break }
        Write-Host "  повтор $try для $f..." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
    }
    if (-not $done) {
        Write-Host "ОШИБКА: не удалось скопировать $f" -ForegroundColor Red
        exit 1
    }
}

# 3. Сверить размеры обоих файлов на плате
$onboard = (mpremote connect $com exec "import os; print(os.stat('w5500_simple.py')[6], os.stat('main.py')[6])" | Out-String).Trim() -split '\s+'
$expW = (Get-Item w5500_simple.py).Length
$expM = (Get-Item main.py).Length
if ([int]$onboard[0] -ne $expW -or [int]$onboard[1] -ne $expM) {
    Write-Host "ОШИБКА: на плате w5500=$($onboard[0]) main=$($onboard[1]), ожидалось w5500=$expW main=$expM" -ForegroundColor Red
    exit 1
}
Write-Host "Файлы на плате: w5500_simple.py=$($onboard[0]), main.py=$($onboard[1]) — совпадают" -ForegroundColor Green

# 4. Сбросить сохранённые настройки MQTT/DI к заводским (новые дефолты из прошивки)
mpremote connect $com exec "import os`ntry: os.remove('mqtt_config.json'); print('mqtt_config.json удалён')`nexcept: print('mqtt_config.json не было')"

# 5. Перезагрузить (обрыв связи при reset — это норма)
try { mpremote connect $com exec "import machine; machine.reset()" 2>$null } catch {}
Write-Host "ГОТОВО: плата на $com прошита и перезагружена." -ForegroundColor Green
exit 0

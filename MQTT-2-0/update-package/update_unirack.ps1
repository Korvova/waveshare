# Обновление прошивки Unirack-1 (исправление одинаковых MAC-адресов).
# Настройки устройства (IP, MQTT) СОХРАНЯЮТСЯ.
# ЗАПУСК: двойной клик по файлу ЗАПУСК.bat (лежит рядом).
$ErrorActionPreference = "Stop"

try {
    Set-Location $PSScriptRoot
    Write-Host "=== Обновление Unirack-1 ===" -ForegroundColor Cyan

    # 0. Найти mpremote (ставится командой: pip install mpremote)
    $mp = $null
    if (Get-Command mpremote -ErrorAction SilentlyContinue) { $mp = @("mpremote") }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m mpremote version *> $null
        if ($LASTEXITCODE -eq 0) { $mp = @("python", "-m", "mpremote") }
    }
    if (-not $mp) {
        throw ("Не найден mpremote. Установите Python с python.org (галочка 'Add to PATH'), " +
               "затем в командной строке выполните:  pip install mpremote  — и запустите снова.")
    }

    # 1. Найти COM-порт платы (Raspberry Pi VID 2E8A)
    $dev = Get-PnpDevice -PresentOnly | Where-Object {
        $_.InstanceId -match 'VID_2E8A' -and $_.FriendlyName -match 'COM\d+'
    } | Select-Object -First 1
    if (-not $dev) {
        throw ("Плата не найдена. Подключите USB-кабель (за передней панелью устройства) " +
               "и проверьте, что кабель с данными, а не 'только зарядка'.")
    }
    $com = [regex]::Match($dev.FriendlyName, 'COM\d+').Value
    Write-Host "Устройство найдено на $com" -ForegroundColor Cyan

    function Invoke-Mp { & $mp[0] $mp[1..($mp.Count-1)] @args; return $LASTEXITCODE }

    # 2. Залить файлы (с повторами: плата может ещё загружаться)
    foreach ($f in @("w5500_simple.py", "main.py")) {
        $done = $false
        foreach ($try in 1..4) {
            $code = Invoke-Mp connect $com cp $f ":$f"
            if ($code -eq 0) { $done = $true; break }
            Write-Host "  повтор $try для $f..." -ForegroundColor Yellow
            Start-Sleep -Seconds 3
        }
        if (-not $done) {
            throw "Не удалось скопировать $f. Отключите/подключите USB и запустите снова."
        }
    }

    # 3. Сверить размеры файлов на плате
    $out = (& $mp[0] $mp[1..($mp.Count-1)] connect $com exec "import os; print(os.stat('w5500_simple.py')[6], os.stat('main.py')[6])" | Out-String).Trim() -split '\s+'
    $expW = (Get-Item w5500_simple.py).Length
    $expM = (Get-Item main.py).Length
    if ([int]$out[0] -ne $expW -or [int]$out[1] -ne $expM) {
        throw "Проверка не сошлась: на плате w5500=$($out[0]) main=$($out[1]), ожидалось $expW / $expM. Запустите скрипт ещё раз."
    }

    # 4. Перезагрузить и показать новый MAC (обрыв связи при reset — это норма)
    $mac = ""
    try {
        $mac = (& $mp[0] $mp[1..($mp.Count-1)] connect $com exec "import machine; u=machine.unique_id(); print('02:08:DC:%02X:%02X:%02X' % (u[-3], u[-2], u[-1]))" | Out-String).Trim()
    } catch {}
    try { Invoke-Mp connect $com exec "import machine; machine.reset()" *> $null } catch {}

    Write-Host ""
    Write-Host "ГОТОВО. Устройство обновлено и перезагружено." -ForegroundColor Green
    if ($mac) { Write-Host "Новый MAC-адрес устройства: $mac" -ForegroundColor Green }
    Write-Host "Настройки IP и MQTT сохранены. MAC также виден в веб-интерфейсе рядом с Board IP."
}
catch {
    Write-Host ""
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    Write-Host ""
    Read-Host "Нажмите Enter для выхода"
}

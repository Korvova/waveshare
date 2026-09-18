# Обновление прошивки Unirack-1 (исправление одинаковых MAC-адресов).
# Настройки устройства (IP, MQTT) СОХРАНЯЮТСЯ.
# ЗАПУСК: двойной клик по файлу ЗАПУСК.bat (лежит рядом).
#
# Два способа заливки: mpremote (если установлен) и резервный — напрямую
# через последовательный порт (raw REPL MicroPython), без Python вообще.
$ErrorActionPreference = "Stop"

# ---------- резервный способ: raw REPL через .NET SerialPort ----------

function Open-Board([string]$port) {
    $sp = New-Object System.IO.Ports.SerialPort $port, 115200
    $sp.Encoding = [System.Text.Encoding]::GetEncoding(28591)
    $sp.DtrEnable = $true
    $sp.RtsEnable = $true
    $sp.WriteTimeout = 5000
    $sp.Open()
    Start-Sleep -Milliseconds 200
    return $sp
}

function Enter-RawRepl($sp) {
    # остановить программу и войти в raw REPL (Ctrl-C, Ctrl-A)
    foreach ($round in 1..4) {
        $sp.Write([byte[]](13, 3, 3), 0, 3)      # Enter + Ctrl-C x2
        Start-Sleep -Milliseconds 300
        $null = $sp.ReadExisting()
        $sp.Write([byte[]](13, 1), 0, 2)         # Enter + Ctrl-A
        $buf = ""
        $deadline = [DateTime]::Now.AddMilliseconds(1500)
        while ([DateTime]::Now -lt $deadline) {
            $buf += $sp.ReadExisting()
            if ($buf.Contains("raw REPL")) { return }
            Start-Sleep -Milliseconds 50
        }
    }
    throw "Плата не переходит в режим обмена (raw REPL). Отключите/подключите USB и запустите снова."
}

function Exec-Raw($sp, [string]$code, [int]$timeoutMs = 8000) {
    $null = $sp.ReadExisting()
    $bytes = [System.Text.Encoding]::ASCII.GetBytes($code)
    $sp.Write($bytes, 0, $bytes.Length)
    $sp.Write([byte[]](4), 0, 1)                 # Ctrl-D = выполнить
    $eot = [string][char]4
    $pat = "(?s)OK(.*?)" + $eot + "(.*?)" + $eot + ">"
    $buf = ""
    $deadline = [DateTime]::Now.AddMilliseconds($timeoutMs)
    while ([DateTime]::Now -lt $deadline) {
        $buf += $sp.ReadExisting()
        if ($buf -match $pat) {
            if ($Matches[2].Trim()) { throw "Ошибка на плате: $($Matches[2].Trim())" }
            return $Matches[1]
        }
        Start-Sleep -Milliseconds 30
    }
    $shown = ($buf -replace "[^ -~]", ".")
    throw "Плата не ответила на команду (получено: '$shown')"
}

function Update-ViaSerial([string]$port, [string[]]$files) {
    Write-Host "Резервный способ: заливка напрямую через последовательный порт..." -ForegroundColor Cyan
    $sp = $null
    try {
        $sp = Open-Board $port
        Enter-RawRepl $sp
        foreach ($f in $files) {
            $data = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $f))
            $chunk = 1024
            $n = [math]::Ceiling($data.Length / $chunk)
            Write-Host -NoNewline "  $f ($($data.Length) байт): "
            for ($i = 0; $i -lt $n; $i++) {
                $off = $i * $chunk
                $len = [math]::Min($chunk, $data.Length - $off)
                $hex = ([System.BitConverter]::ToString($data, $off, $len)) -replace "-", ""
                $mode = if ($i -eq 0) { "wb" } else { "ab" }
                $code = "f=open('$f','$mode')`nf.write(bytes.fromhex('$hex'))`nf.close()"
                $null = Exec-Raw $sp $code
                Write-Host -NoNewline "."
            }
            Write-Host " готово"
        }
        # сверка размеров
        $out = (Exec-Raw $sp "import os`nprint(os.stat('w5500_simple.py')[6], os.stat('main.py')[6])").Trim() -split "\s+"
        $expW = (Get-Item (Join-Path $PSScriptRoot "w5500_simple.py")).Length
        $expM = (Get-Item (Join-Path $PSScriptRoot "main.py")).Length
        if ([int]$out[0] -ne $expW -or [int]$out[1] -ne $expM) {
            throw "Проверка не сошлась: на плате w5500=$($out[0]) main=$($out[1]), ожидалось $expW / $expM. Запустите скрипт ещё раз."
        }
        $mac = (Exec-Raw $sp "import machine`nu=machine.unique_id()`nprint('02:08:DC:%02X:%02X:%02X' % (u[-3], u[-2], u[-1]))").Trim()
        # перезагрузка (ответа не будет — это норма)
        $rb = [System.Text.Encoding]::ASCII.GetBytes("import machine`nmachine.reset()")
        $sp.Write($rb, 0, $rb.Length)
        $sp.Write([byte[]](4), 0, 1)
        Start-Sleep -Milliseconds 300
        return $mac
    }
    finally { try { if ($sp -and $sp.IsOpen) { $sp.Close() } } catch {} }
}

function Stop-Firmware([string]$port) {
    $sp = $null
    try {
        $sp = Open-Board $port
        $bytes = [byte[]](13, 3, 3)
        foreach ($i in 1..5) { $sp.Write($bytes, 0, 3); Start-Sleep -Milliseconds 300 }
    } catch {}
    finally { try { if ($sp -and $sp.IsOpen) { $sp.Close() } } catch {} }
    Start-Sleep -Milliseconds 300
}

# ---------- основной ход ----------

try {
    Set-Location $PSScriptRoot
    Write-Host "=== Обновление Unirack-1 ===" -ForegroundColor Cyan

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

    # 2. Найти mpremote (основной способ); без него сразу резервный
    $mpExe = $null
    $mpPre = @()
    if (Get-Command mpremote -ErrorAction SilentlyContinue) {
        $mpExe = "mpremote"
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m mpremote version *> $null
        if ($LASTEXITCODE -eq 0) { $mpExe = "python"; $mpPre = @("-m", "mpremote") }
    }
    function Invoke-Mp { & $script:mpExe @script:mpPre @args; return $LASTEXITCODE }

    $files = @("w5500_simple.py", "main.py")
    $mac = ""
    $done = $false

    if ($mpExe) {
        Write-Host "Пробую основной способ (mpremote)..."
        Stop-Firmware $com
        $mpOk = $true
        foreach ($f in $files) {
            $sent = $false
            foreach ($try in 1..2) {
                $code = Invoke-Mp connect $com cp $f ":$f"
                if ($code -eq 0) { $sent = $true; break }
                Start-Sleep -Seconds 2
                Stop-Firmware $com
            }
            if (-not $sent) { $mpOk = $false; break }
        }
        if ($mpOk) {
            $out = (& $mpExe @mpPre connect $com exec "import os; print(os.stat('w5500_simple.py')[6], os.stat('main.py')[6])" | Out-String).Trim() -split '\s+'
            $expW = (Get-Item "w5500_simple.py").Length
            $expM = (Get-Item "main.py").Length
            if ([int]$out[0] -eq $expW -and [int]$out[1] -eq $expM) {
                try {
                    $mac = (& $mpExe @mpPre connect $com exec "import machine; u=machine.unique_id(); print('02:08:DC:%02X:%02X:%02X' % (u[-3], u[-2], u[-1]))" | Out-String).Trim()
                } catch {}
                try { Invoke-Mp connect $com exec "import machine; machine.reset()" *> $null } catch {}
                $done = $true
            }
        }
        if (-not $done) {
            Write-Host "mpremote не справился — переключаюсь на резервный способ." -ForegroundColor Yellow
        }
    }

    if (-not $done) {
        $mac = Update-ViaSerial $com $files
        $done = $true
    }

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

@echo off
setlocal EnableExtensions

title Jatibarang CCUS Workbench Launcher

cd /d "%~dp0"
set "ROOT=%CD%"
set "FRONTEND=%CD%\frontend"
set "APP_URL=http://127.0.0.1:5173/"
set "API_URL=http://127.0.0.1:8000/health"

echo.
echo  Jatibarang CCUS Screening Workbench
echo  ===================================
echo.

where python.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.11 or newer, then run this launcher again.
  goto :failed
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.11 or newer is required.
  python --version
  goto :failed
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm was not found on PATH.
  echo Install a current Node.js LTS release, then run this launcher again.
  goto :failed
)

if not exist "%ROOT%\pyproject.toml" (
  echo [ERROR] pyproject.toml was not found under:
  echo         %ROOT%
  goto :failed
)

if not exist "%FRONTEND%\package.json" (
  echo [ERROR] frontend\package.json was not found.
  goto :failed
)

python -m pip show jatibarang-ccus-framework >nul 2>&1
if errorlevel 1 (
  echo [SETUP] Installing Python runtime dependencies...
  python -m pip install -e .
  if errorlevel 1 (
    echo [ERROR] Python dependency installation failed.
    goto :failed
  )
)

if not exist "%FRONTEND%\node_modules" (
  echo [SETUP] Installing frontend dependencies...
  pushd "%FRONTEND%"
  call npm.cmd install
  if errorlevel 1 (
    popd
    echo [ERROR] Frontend dependency installation failed.
    goto :failed
  )
  popd
)

powershell.exe -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%API_URL%' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if errorlevel 1 (
  echo [START] Backend on http://127.0.0.1:8000
  start "Jatibarang Backend :8000" /min cmd.exe /d /k "cd /d ""%ROOT%"" && python -m uvicorn jatibarang_ccus.api.app:app --app-dir src --host 127.0.0.1 --port 8000"
) else (
  echo [READY] Backend is already running on port 8000.
)

powershell.exe -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%' -TimeoutSec 2; if ($response.Content -match 'Jatibarang CCUS Screening Workbench') { exit 0 } } catch {}; exit 1" >nul 2>&1
if errorlevel 1 (
  echo [START] Frontend on http://127.0.0.1:5173
  start "Jatibarang Frontend :5173" /min cmd.exe /d /k "cd /d ""%FRONTEND%"" && npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort"
) else (
  echo [READY] Frontend is already running on port 5173.
)

echo [WAIT] Waiting for the browser app to become ready...
powershell.exe -NoProfile -Command "$deadline = (Get-Date).AddSeconds(90); do { try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%' -TimeoutSec 2; if ($response.Content -match 'Jatibarang CCUS Screening Workbench') { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] The frontend did not become ready within 90 seconds.
  echo Check the Backend and Frontend console windows for details.
  goto :failed
)

echo [OPEN] %APP_URL%
if /i "%JATIBARANG_NO_BROWSER%"=="1" (
  echo [READY] Browser opening was skipped for launcher validation.
  exit /b 0
)
start "" "%APP_URL%"
exit /b 0

:failed
echo.
pause
exit /b 1

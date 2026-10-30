@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo [1/3] Installing Python dependencies...
  py -3 -m venv backend\.venv || goto :err
  backend\.venv\Scripts\python -m pip install -r backend\requirements.txt || goto :err
)
if not exist frontend\dist\index.html (
  echo [2/3] Building the frontend...
  pushd frontend
  call npm ci || (popd & goto :err)
  call npm run build || (popd & goto :err)
  popd
)
echo [3/3] Starting http://127.0.0.1:8765
if not defined NO_BROWSER start "" http://127.0.0.1:8765
backend\.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
goto :eof
:err
echo FAILED - see messages above.
pause
exit /b 1

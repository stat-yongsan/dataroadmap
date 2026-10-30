@echo off
setlocal
cd /d "%~dp0"
rem Data Roadmap app - starts on http://127.0.0.1:8765 . First run builds the venv and the web screens.
rem This file is ASCII + CRLF on purpose: cmd.exe mis-parses UTF-8 Korean / LF batch files.
if not exist backend\.venv\Scripts\python.exe (
  echo [1/3] Creating Python venv and installing packages...
  py -3 -m venv backend\.venv || goto :err
  backend\.venv\Scripts\python -m pip install -r backend\requirements.txt || goto :err
)
if not exist frontend\dist\index.html (
  echo [2/3] Building web screens...
  pushd frontend
  call npm ci || (popd & goto :err)
  call npm run build || (popd & goto :err)
  popd
)
echo [3/3] Starting http://127.0.0.1:8765  (press Ctrl+C in this window to stop)
if not defined NO_BROWSER start "" http://127.0.0.1:8765
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
goto :eof
:err
echo FAILED - see the messages above.
pause
exit /b 1

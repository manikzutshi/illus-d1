@echo off
rem Start the Illustration Engine Schematic Studio with the project's own virtual environment.
rem Usage (from PowerShell or cmd, in this folder):   .\studio            then open http://127.0.0.1:8765
rem Extra options are passed through, e.g.            .\studio --port 9000
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo Virtual environment not found at %ROOT%.venv - create it with:  python -m venv .venv ^&^& .venv\Scripts\pip install -e .
  exit /b 1
)
if not exist "%ROOT%frontend\dist\index.html" (
  echo Frontend not built yet - run:  cd frontend ^&^& npm install ^&^& npm run build
)
if "%GEMINI_API_KEY%"=="" echo Note: GEMINI_API_KEY is not set in this terminal - AI generation will be unavailable; examples still work.
cd /d "%ROOT%"
"%ROOT%.venv\Scripts\python.exe" -m cli.main studio serve %*

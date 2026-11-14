@echo off
rem Double-click to build IDRA for this Windows 10/11 PC.
setlocal
cd /d "%~dp0"
echo Building IDRA for Windows. The first build takes 5-15 minutes; leave this window open.
echo.
set "PYEXE="
set "PYARGS="
for %%V in (3.13 3.12 3.11 3.14) do (
  if not defined PYEXE (
    py -%%V -c "import sys" >nul 2>&1 && (
      set "PYEXE=py"
      set "PYARGS=-%%V"
    )
  )
)
if not defined PYEXE (
  python -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<(3,15) else 1)" >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
  where winget >nul 2>&1
  if errorlevel 1 goto nopython
  echo Installing Python 3.13 with winget ^(one-time^)...
  winget install -e --id Python.Python.3.13 --scope user --accept-source-agreements --accept-package-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
)
if not defined PYEXE goto nopython
"%PYEXE%" %PYARGS% packaging\build_app.py %*
if errorlevel 1 goto failed
echo.
echo Finished. The dist folder will open.
start "" "%~dp0dist"
goto end
:nopython
echo Python 3.11-3.14 is needed. Install it from https://www.python.org/downloads/windows/
echo ^(tick "Add python.exe to PATH"^), or run:  winget install Python.Python.3.13
goto end
:failed
echo.
echo The build stopped. The reason is printed in red above.
:end
echo.
pause

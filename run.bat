@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  Football Heatmap - one click analysis
echo ============================================
echo(
where python >nul 2>nul
if errorlevel 1 goto NOPY
python -c "import numpy,pandas,scipy,matplotlib,PIL,folium" >nul 2>nul
if errorlevel 1 goto INSTALL
goto RUN
:INSTALL
echo [setup] installing dependencies ...
python -m pip install -q -r requirements.txt
if errorlevel 1 goto PIPFAIL
:RUN
echo(
echo If data\raw is empty, a synthetic sample will be generated first.
echo(
dir /b data\raw\*.gpx >nul 2>nul
if errorlevel 1 python tools\make_sample_data.py
echo(
echo Questionnaire: switch ends? which goal attacked? your position per half?
echo Press Enter to keep the value in brackets.
echo(
python src\session_wizard.py
echo(
python src\run_all.py %*
set RC=%ERRORLEVEL%
echo(
if not "%RC%"=="0" goto FAIL
echo [done] results:
echo   output\figures\   charts
echo   output\tables\    csv
echo   output\panel.html frontend panel
echo   report\          markdown reports
echo(
if exist "output\panel.html" start "" "output\panel.html"
goto END
:NOPY
echo [error] python not found. Install Python 3.10+ and enable Add to PATH.
goto END
:PIPFAIL
echo [error] pip install failed. Run manually: python -m pip install -r requirements.txt
goto END
:FAIL
echo [error] analysis failed with exit code %RC%.
goto END
:END
pause

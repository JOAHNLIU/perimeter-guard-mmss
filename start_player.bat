@echo off
rem Запускає локальний вебсервер для ЛР 2 і відкриває плеєр в Microsoft Edge.
rem Закривати це вікно не можна, доки тривають вимірювання.
chcp 65001 >nul
cd /d "%~dp0stream"
start "" cmd /c "timeout /t 2 >nul & start msedge http://localhost:8000/player.html"
python -m http.server 8000 || py -m http.server 8000

@echo off
cd /d "%~dp0"

echo ========================================
echo       SEVENTH GATE - GITHUB UPDATE
echo ========================================
echo.

git add .
git commit -m "Update Seventh Gate"
git push

echo.
echo ========================================
echo              FINISHED
echo ========================================
pause
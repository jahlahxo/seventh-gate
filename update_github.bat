@echo off
cd /d "%~dp0"

echo ========================================
echo       SEVENTH GATE - GITHUB UPDATE
echo ========================================
echo.

echo Running full project check...
echo.

python project_check.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo       TESTS FAILED - NOT PUSHING
    echo ========================================
    echo.
    echo GitHub has NOT been updated.
    echo Fix the project first, then try again.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo          PROJECT CHECK PASSED
echo ========================================
echo.
echo Preparing GitHub update...
echo.

git add .

if errorlevel 1 (
    echo.
    echo Git add failed. Nothing was pushed.
    pause
    exit /b 1
)

git diff --cached --quiet

if not errorlevel 1 (
    echo.
    echo No changes to upload. GitHub is already current.
    echo.
    pause
    exit /b 0
)

git commit -m "Update Seventh Gate"

if errorlevel 1 (
    echo.
    echo Git commit failed. Nothing was pushed.
    pause
    exit /b 1
)

git push

if errorlevel 1 (
    echo.
    echo ========================================
    echo             PUSH FAILED
    echo ========================================
    echo.
    echo Your local files are safe, but GitHub was not updated.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo       GITHUB UPDATE SUCCESSFUL
echo ========================================
echo.
pause
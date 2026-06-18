@echo off
REM Build Price Tracker into a standalone Windows app folder.
REM Usage: build.bat   (run from the project root)

call venv\Scripts\activate.bat || (echo Could not activate venv & exit /b 1)

echo Installing build dependencies...
pip install -r requirements-dev.txt || exit /b 1

echo Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building...
pyinstaller PriceTracker.spec --noconfirm || exit /b 1

echo.
echo Done. Run:  dist\PriceTracker\PriceTracker.exe

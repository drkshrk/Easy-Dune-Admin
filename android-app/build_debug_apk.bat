@echo off
setlocal

cd /d "%~dp0"

if not exist ".\gradlew.bat" (
    echo Gradle wrapper was not found in this folder.
    echo Open this android-app folder in Android Studio, or regenerate the wrapper with:
    echo gradle wrapper --gradle-version 8.9
    exit /b 1
)

call ".\gradlew.bat" assembleDebug
if errorlevel 1 (
    echo.
    echo APK build failed. Check the Gradle output above.
    exit /b %errorlevel%
)

echo.
echo Debug APK:
echo %~dp0app\build\outputs\apk\debug\EDA.apk

endlocal

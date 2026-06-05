$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".\gradlew.bat")) {
    Write-Host "Gradle wrapper was not found in this folder."
    Write-Host "Open this android-app folder in Android Studio, or regenerate the wrapper with: gradle wrapper --gradle-version 8.9"
    exit 1
}

.\gradlew.bat assembleDebug
Write-Host ""
Write-Host "Debug APK:"
Write-Host "$PSScriptRoot\app\build\outputs\apk\debug\EDA.apk"

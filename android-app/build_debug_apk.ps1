$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command gradle -ErrorAction SilentlyContinue)) {
    Write-Host "Gradle was not found on PATH."
    Write-Host "Open this android-app folder in Android Studio, or install Gradle and the Android SDK, then rerun this script."
    exit 1
}

gradle assembleDebug
Write-Host ""
Write-Host "Debug APK:"
Write-Host "$PSScriptRoot\app\build\outputs\apk\debug\EDA.apk"

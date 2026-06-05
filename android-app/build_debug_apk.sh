#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v gradle >/dev/null 2>&1; then
    echo "Gradle was not found on PATH."
    echo "Open this android-app folder in Android Studio, or install Gradle and the Android SDK, then rerun this script."
    exit 1
fi

gradle assembleDebug
echo
echo "Debug APK:"
echo "$(pwd)/app/build/outputs/apk/debug/EDA.apk"

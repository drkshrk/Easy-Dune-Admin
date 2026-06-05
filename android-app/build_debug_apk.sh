#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x "./gradlew" ]; then
    echo "Gradle wrapper was not found or is not executable in this folder."
    echo "Run: chmod +x gradlew"
    echo "If the wrapper is missing, regenerate it with: gradle wrapper --gradle-version 8.9"
    exit 1
fi

./gradlew assembleDebug
echo
echo "Debug APK:"
echo "$(pwd)/app/build/outputs/apk/debug/EDA.apk"

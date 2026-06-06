# Easy Dune Admin Android APK

This folder contains a sideloadable Android WebView wrapper for Easy Dune Admin.
It does not bundle the Flask webadmin or RedBlink stack into the phone. It opens
your existing Easy Dune Admin server over LAN or VPN.

## Build With Android Studio

1. Install Android Studio on Windows.
2. Open this `android-app` folder as a project.
3. Let Android Studio install the Android Gradle Plugin and SDK platform if it asks.
4. Build `app` with `Build > Build Bundle(s) / APK(s) > Build APK(s)`.
5. The debug APK appears under:

```text
android-app/app/build/outputs/apk/debug/EDA.apk
```

## Build From A Terminal

The Android project includes the Gradle wrapper, so builders do not need to
install Gradle separately. Java 17 and the Android SDK are still required.

Windows PowerShell:

```powershell
cd android-app
.\gradlew.bat assembleDebug
```

Linux/macOS:

```bash
cd android-app
chmod +x gradlew
./gradlew assembleDebug
```

The APK is written to:

```text
android-app/app/build/outputs/apk/debug/EDA.apk
```

If the build reaches Android SDK checks and fails on licenses or missing
packages, repair the local SDK first:

```powershell
$env:ANDROID_SDK_ROOT="$env:LOCALAPPDATA\Android\Sdk"
& "$env:ANDROID_SDK_ROOT\cmdline-tools\latest\bin\sdkmanager.bat" --install "platforms;android-35" "build-tools;34.0.0" "platform-tools"
& "$env:ANDROID_SDK_ROOT\cmdline-tools\latest\bin\sdkmanager.bat" --licenses
```

If Gradle reports `package.xml (Access is denied)`, fix the Android SDK folder
permissions or reinstall the affected SDK platform/build-tools through Android
Studio's SDK Manager.

## Install On Android

1. Copy `EDA.apk` to the phone by USB, file share, cloud drive, or Android file transfer.
2. Open it from Files or your file manager.
3. Android will usually block the first install attempt because the APK was not installed from Google Play.
4. When prompted, open the Android settings screen for that file manager/browser and allow installs from that source.
5. Return to the APK and continue the install.
6. Launch Easy Dune Admin.
7. Enter the Easy Dune Admin URL, for example:

```text
http://SERVER-IP:8089
```

or:

```text
https://eda.example.com
```

No rooted phone is required. To update an existing sideloaded install, build a
new `EDA.apk` and install it over the old one.

Admin users can reach Developer Tools from the webadmin hamburger menu inside
the Android app. The Developer page still requires the separate Developer key
before research commands are visible.

## Release Packaging

- Commit the Android wrapper source under `android-app/`.
- Do not commit generated APK/AAB/build output.
- Attach `EDA.apk` to GitHub Releases only as an optional convenience artifact.
- Suggested release wording:

```text
Optional Android WebView wrapper. Sideload at your own discretion. Android will block the first install attempt because this APK is not from Google Play; allow installs from that source if you trust this release. The APK stores only the configured Easy Dune Admin server URL and defaults to http://127.0.0.1:8089.
```

## Notes

- The app permits cleartext HTTP because Easy Dune Admin is often used on LAN/VPN.
- Keep the webadmin private. Do not expose it directly to the public internet.
- Use HTTPS or a VPN if you later run it outside a trusted LAN.
- The APK stores only the server URL in Android app preferences.
- The distributed default URL is `http://127.0.0.1:8089` so prebuilt APKs do not expose any private LAN topology.

# Local build reference

Use [INSTALL.md](INSTALL.md) for the short phone-install path. Expo supplies local project-generation tools. The scripts use local Gradle and Xcode builds.

## Toolchains

| Platform | Install once                                                         | Check                                      |
| -------- | -------------------------------------------------------------------- | ------------------------------------------ |
| Both     | Node 22.20.0 and npm                                                 | `node --version`                           |
| Android  | Android Studio, Android SDK, command-line tools, and its bundled JDK | The build prints its selected Java version |
| iPhone   | Full Xcode with iOS support, its command-line tools, and CocoaPods   | `xcodebuild -version` and `pod --version`  |

Open each IDE once to finish its setup. Accept the required SDK licenses. On macOS, select Xcode under **Xcode → Settings → Locations → Command Line Tools**. CocoaPods can be installed with `brew install cocoapods`.

The Android helper reads `ANDROID_HOME` or `ANDROID_SDK_ROOT`. It also checks the standard Android Studio SDK directory for the current OS.

The helper prefers Android Studio's bundled JDK when `JAVA_HOME` is unset. Its Java 25 works with the included Gradle 9.4.1. An explicit `JAVA_HOME` in `.env.local` or the shell takes precedence. The helper validates Java 17 through 26 and passes the selected JDK to Gradle. It does not change the system default.

To select Android Studio's Java on macOS, put this line in the ignored `.env.local` file:

```dotenv
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
```

Expo requires machine-specific variables such as `JAVA_HOME` in `.env.local`, not `.env`. Keep Datadog credentials in `.env`. The helper loads both files, with `.env.local` taking precedence.

If Android Studio is installed elsewhere, use its JDK directory. JDK 17 is an alternative. On macOS, install it with `brew install openjdk@17`.

`Unsupported class file major version 71` means Java 27 bytecode. Gradle 9.4.1 cannot run with Java 27. Select a compatible JDK instead of upgrading Gradle independently of Expo. See the [Gradle Java compatibility table](https://docs.gradle.org/current/userguide/compatibility.html).

See the official [local compilation guide](https://docs.expo.dev/guides/local-app-development/) and [Android command-line build guide](https://developer.android.com/build/building-cmdline).

## API addresses

| Target                           | API address                        |
| -------------------------------- | ---------------------------------- |
| Physical phone on the same Wi-Fi | `http://YOUR_COMPUTER_LAN_IP:4310` |
| iOS simulator                    | `http://localhost:4310`            |
| Android Studio emulator          | `http://10.0.2.2:4310`             |
| Shared hosted demo               | Your HTTPS API URL                 |

`setup:device` is for physical phones. It rejects loopback addresses, suggests a LAN address, and stores your choice in `.env`. `api:device` binds to the LAN. Both devices must be on a network that permits device-to-device traffic.

For PostgreSQL, set `API_BIND_HOST=0.0.0.0` in `.env` and run `make up` instead of `npm run api:device`. Do not run both APIs on port 4310.

`ALLOW_LOCAL_HTTP=true` enables local HTTP in the generated native projects. Use it only for a trusted LAN demo. Use HTTPS and set this flag to `false` for a shared hosted API. Rebuild after changes.

## Android APK

`npm run build:android` checks the toolchain and API, refreshes the native project, and runs Gradle `assembleRelease`. It copies the APK to `artifacts/fieldwork-one.apk`.

The generated template signs this sample APK with its local debug key. This permits direct demo installation. Use your own release signing configuration for distribution beyond the sample. Do not commit keystores or passwords.

Run `npm run install:android` to build the APK, then start the local QR server. A failed build prevents the server from starting. Use `npm run serve:android` to share an existing APK without rebuilding. Scan the QR code with the phone camera and tap the download button. Open the printed URL on your computer for a larger QR code. Both devices must use the same Wi-Fi.

The server uses port 4311. It selects a local IPv4 address, with a preference for the API host in `.env`. If it selects the wrong interface, use `npm run serve:android -- --host YOUR_LAN_IP --port 4311`. The same options work with `install:android`. Allow incoming connections if the computer firewall requests permission. Guest networks can block device-to-device traffic.

The server exposes only the install page, QR image, and APK. It generates the QR code locally. It does not upload files or serve the project directory. Press **Ctrl+C** after installation to stop sharing. Keep the API running separately. The QR installer is for Android only.

Connect a phone with USB debugging enabled to install through the SDK tools:

```sh
adb install -r artifacts/fieldwork-one.apk
```

For an API over USB, use `adb reverse tcp:4310 tcp:4310` with `EXPO_PUBLIC_API_URL=http://localhost:4310`. Use the development command below for that configuration; the physical-phone helper expects a LAN address.

## iPhone signing

`npm run prepare:ios` generates the native project, installs Pods, and opens the workspace. Sign in to your Apple account in Xcode. Select the app target, enable automatic signing, and choose your team. Connect and trust the phone.

`npm run build:ios` refreshes the project, installs Pods, and runs the local device build with the Release configuration. It includes the JavaScript bundle and does not start Metro. Choose the physical iPhone when prompted.

Native refreshes use `--no-clean` to preserve the Xcode signing selection. You can also set `IOS_APPLE_TEAM_ID` in `.env` to retain the team when native directories are recreated. Change the bundle identifier in `app.config.ts` if your team cannot register the default identifier.

A Personal Team supports testing on personal devices, with provisioning limits. Broader distribution and APNs require the applicable Apple developer membership and provisioning. An unsigned IPA cannot be installed directly. See [Apple account and signing requirements](https://developer.apple.com/help/account/basics/about-your-developer-account).

## Simulators and source editing

Set the appropriate API address in `.env`. For a local development build with Metro:

```sh
npm run android
# Or, on macOS:
npm run ios
```

These commands use your local native tools. An iOS simulator build cannot be installed on an iPhone. Use the sample evidence image when a camera is unavailable.

The build helpers regenerate native configuration before compiling. If you use raw native tools after a plugin or permission change, run:

```sh
npx expo prebuild --no-install --no-clean
```

Keep native configuration in `app.config.ts` and config plugins. Generated `ios/` and `android/` directories are ignored by Git.

## Optional native push

Local notifications work without remote push setup. Remote token registration is off by default, so local iPhone testing does not require the APNs entitlement.

For native token registration, set `EXPO_PUBLIC_NATIVE_PUSH_ENABLED=true`, configure APNs or FCM, and rebuild. Android can read a local Firebase configuration through `ANDROID_GOOGLE_SERVICES_FILE`. The app requests a native APNs or FCM token. It does not use an Expo push service. The sample stores the token but has no remote push sender.

## Troubleshooting

| Symptom                                           | Check                                                                     |
| ------------------------------------------------- | ------------------------------------------------------------------------- |
| API health check fails                            | Start the API, confirm the LAN address, and open `/health` from the phone |
| Android SDK or Java is missing                    | Install the SDK and JDK; check `ANDROID_HOME` and `JAVA_HOME`             |
| Xcode check fails                                 | Install full Xcode and select its command-line tools                      |
| CocoaPods check fails                             | Install CocoaPods and ensure `pod` is on `PATH`                           |
| No signing certificate                            | Open the workspace with `prepare:ios` and select your Apple team          |
| iPhone app expires                                | Rebuild and reinstall with a valid provisioning profile                   |
| New Datadog values have no effect                 | Edit `.env`, rebuild, and reinstall; restart Metro for debug builds       |
| Native HTTP or permission settings have no effect | Rebuild; these values are native configuration                            |

A JavaScript export does not prove that a native binary builds or installs. Check [VALIDATION.md](VALIDATION.md) for completed and pending checks.

# Install on a phone

Build on your computer. No build-service account or app-store listing is required.

**Install once:** Node 22.20.0. For Android, install Android Studio and its SDK. The helper can use Android Studio's bundled Java 25. For iPhone, use a Mac with Xcode and CocoaPods. See [toolchain setup](BUILDING.md#toolchains).

## 1. Prepare

From the repository root:

```sh
cd datadog/fieldwork-mobile-demo
nvm use
npm run setup:device
```

Confirm the suggested laptop LAN address. The script installs dependencies and writes `.env`. Existing credentials are preserved.

Put the Datadog application ID and client token in this same `.env` file. See [the credential values](DATADOG.md#native-client-configuration). Credentials are optional for running the sample.

## 2. Start the API

```sh
npm run api:device
```

Keep this terminal open. Put the phone on the same Wi-Fi. Open the printed `/health` URL from the phone.

## 3. Build and install

### Android

In another terminal:

```sh
npm run install:android
```

The command builds the APK, then starts the QR server. It stops if the build fails.

Scan the terminal QR code with the phone camera. Tap **Download APK**, open the file, and allow installation from that browser. Keep both devices on the same Wi-Fi. Press **Ctrl+C** after installation to stop sharing.

The APK includes JavaScript and uses a local demo signing key. Metro is not required.

### iPhone

Connect and trust the iPhone. Prepare the Xcode workspace once:

```sh
npm run prepare:ios
```

In Xcode, select the **FieldworkOne** target. Under **Signing & Capabilities**, enable automatic signing and select your Apple team. Then run:

```sh
npm run install:ios
```

The command builds the app for the connected iPhone, then installs and opens it. It stops if the build fails. If more than one iPhone is available, add `-- --device "NAME"`. Enable Developer Mode if iOS requests it.

A free Personal Team can test on its own devices, but its provisioning expires after seven days. [Apple signing limits](https://developer.apple.com/help/account/basics/about-your-developer-account)

Keep the API running. Rebuild after changes to credentials or the API address. Testers who receive an APK only need the install step. iPhone installation still requires valid signing for that device.

For simulators, source editing, signing, or troubleshooting, see [BUILDING.md](BUILDING.md). Expo Go cannot run the native Datadog modules.

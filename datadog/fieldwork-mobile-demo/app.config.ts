import "dotenv/config";
import { ExpoConfig } from "expo/config";

const upload = process.env.DATADOG_UPLOAD_ENABLED === "true";
const nativePush = process.env.EXPO_PUBLIC_NATIVE_PUSH_ENABLED === "true";
const allowHttp = process.env.ALLOW_LOCAL_HTTP === "true";
const config: ExpoConfig = {
  name: "Fieldwork One",
  slug: "fieldwork-one-demo",
  version: "1.0.0",
  orientation: "portrait",
  scheme: "fieldwork-one",
  userInterfaceStyle: "light",
  icon: "./assets/icon.png",
  ios: {
    bundleIdentifier: "ai.oodle.fieldworkdemo",
    ...(process.env.IOS_APPLE_TEAM_ID
      ? { appleTeamId: process.env.IOS_APPLE_TEAM_ID }
      : {}),
    supportsTablet: true,
    infoPlist: {
      ITSAppUsesNonExemptEncryption: false,
      NSLocalNetworkUsageDescription:
        "Connect to the demo API on your development computer.",
      NSAppTransportSecurity: {
        NSAllowsLocalNetworking: allowHttp,
        NSAllowsArbitraryLoads: allowHttp,
      },
    },
  },
  android: {
    package: "ai.oodle.fieldworkdemo",
    ...(process.env.ANDROID_GOOGLE_SERVICES_FILE
      ? { googleServicesFile: process.env.ANDROID_GOOGLE_SERVICES_FILE }
      : {}),
    adaptiveIcon: {
      foregroundImage: "./assets/icon.png",
      backgroundColor: "#113c31",
    },
  },
  web: {
    bundler: "metro",
    favicon: "./assets/icon.png",
    name: "Fieldwork One",
  },
  plugins: [
    "expo-dev-client",
    "expo-secure-store",
    [
      "expo-image-picker",
      {
        photosPermission: "Select a photo as evidence for a demo job.",
        cameraPermission: "Take a photo as evidence for a demo job.",
        microphonePermission: false,
      },
    ],
    [
      "expo-location",
      {
        locationWhenInUsePermission:
          "Show your current location while you view the route.",
      },
    ],
    ["expo-notifications", { enableRemoteNotifications: nativePush }],
    ["./scripts/with-local-signing.js", { nativePush }],
    [
      "expo-datadog",
      {
        errorTracking: {
          iosDsyms: upload,
          iosSourcemaps: upload,
          androidSourcemaps: upload,
          androidProguardMappingFiles: upload,
          serviceName: "fieldwork-one-mobile",
        },
      },
    ],
    ["./scripts/with-local-http.js", { enabled: allowHttp }],
  ],
};
export default config;

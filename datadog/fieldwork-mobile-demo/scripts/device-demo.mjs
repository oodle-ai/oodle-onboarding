import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  access,
  copyFile,
  mkdir,
  readFile,
  rename,
  writeFile,
} from "node:fs/promises";
import { homedir, networkInterfaces } from "node:os";
import { delimiter, join } from "node:path";
import { createInterface } from "node:readline/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const command = process.argv[2];
const envPath = join(root, ".env");
const npmCli = process.env.npm_execpath;
let values = {};
let parseEnv;

function runTool(executable, args, { cwd = root, quiet = false } = {}) {
  const result = spawnSync(executable, args, {
    cwd,
    env: { ...process.env, ...values },
    stdio: quiet ? "ignore" : "inherit",
  });
  if (!quiet && result.error) throw result.error;
  if (!quiet && result.status !== 0)
    throw new Error(`The command failed (${result.status ?? result.signal}).`);
  return result.status;
}

const run = (script, args, options) =>
  runTool(process.execPath, [script, ...args], options);
const expo = (args) => run(join(root, "node_modules/expo/bin/cli"), args);

async function androidTools() {
  const defaultSdk =
    process.platform === "darwin"
      ? join(homedir(), "Library/Android/sdk")
      : process.platform === "win32"
        ? join(
            process.env.LOCALAPPDATA || join(homedir(), "AppData/Local"),
            "Android/Sdk",
          )
        : join(homedir(), "Android/Sdk");
  values.ANDROID_HOME =
    values.ANDROID_HOME ||
    values.ANDROID_SDK_ROOT ||
    process.env.ANDROID_HOME ||
    process.env.ANDROID_SDK_ROOT ||
    defaultSdk;
  try {
    await access(values.ANDROID_HOME);
  } catch {
    throw new Error(
      "Install the Android SDK and set ANDROID_HOME. See docs/BUILDING.md.",
    );
  }
  const executable = process.platform === "win32" ? "java.exe" : "java";
  const inspect = (home) => {
    const result = spawnSync(
      home ? join(home, "bin", executable) : executable,
      ["-XshowSettings:properties", "-version"],
      { encoding: "utf8" },
    );
    const output = `${result.stdout || ""}\n${result.stderr || ""}`;
    return {
      home: output.match(/^\s*java.home\s*=\s*(.+)$/m)?.[1]?.trim(),
      version: output
        .match(/^\s*java.specification.version\s*=\s*(.+)$/m)?.[1]
        ?.trim(),
      ok: result.status === 0,
    };
  };
  const explicitHome = values.JAVA_HOME || process.env.JAVA_HOME;
  const supported = (item) =>
    item.ok &&
    item.home &&
    Number(item.version) >= 17 &&
    Number(item.version) <= 26;
  let jdk;
  if (explicitHome) {
    jdk = inspect(explicitHome);
    if (!supported(jdk))
      throw new Error(
        `JAVA_HOME selects Java ${jdk.version || "unknown"}. The included Gradle supports Java 17 through 26. Select a compatible JDK in .env.local or your shell. See docs/BUILDING.md.`,
      );
  } else {
    const candidates = [];
    if (process.platform === "darwin") {
      candidates.push(
        "/Applications/Android Studio.app/Contents/jbr/Contents/Home",
        join(
          homedir(),
          "Applications/Android Studio.app/Contents/jbr/Contents/Home",
        ),
      );
      const found = spawnSync("/usr/libexec/java_home", ["-v", "17", "-F"], {
        encoding: "utf8",
      });
      if (found.status === 0) candidates.push(found.stdout.trim());
      candidates.push(
        "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home",
        "/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home",
      );
    } else if (process.platform === "win32") {
      candidates.push(
        join(
          process.env.ProgramFiles || "C:\\Program Files",
          "Android/Android Studio/jbr",
        ),
      );
    } else {
      candidates.push(
        "/opt/android-studio/jbr",
        "/usr/local/android-studio/jbr",
      );
    }
    candidates.push(undefined);
    for (const candidate of candidates) {
      const inspected = inspect(candidate);
      if (supported(inspected)) {
        jdk = inspected;
        break;
      }
    }
  }
  if (!jdk?.home)
    throw new Error(
      "No compatible JDK was found. Use Android Studio's bundled JDK or install JDK 17 and set JAVA_HOME. See docs/BUILDING.md.",
    );
  const compiler = join(
    jdk.home,
    "bin",
    process.platform === "win32" ? "javac.exe" : "javac",
  );
  if (runTool(compiler, ["-version"], { quiet: true }) !== 0)
    throw new Error(
      "JAVA_HOME must select a full JDK with javac, not a Java runtime.",
    );
  values.JAVA_HOME = jdk.home;
  values.PATH = `${join(jdk.home, "bin")}${delimiter}${values.PATH || process.env.PATH || ""}`;
  console.log(`Android build: Java ${jdk.version} at ${jdk.home}`);
}

function iosTools() {
  if (process.platform !== "darwin")
    throw new Error("Local iPhone builds require macOS and Xcode.");
  if (runTool("xcodebuild", ["-version"], { quiet: true }) !== 0)
    throw new Error(
      "Install full Xcode and select its command-line tools. See docs/BUILDING.md.",
    );
  if (runTool("pod", ["--version"], { quiet: true }) !== 0)
    throw new Error(
      "Install CocoaPods before building for iPhone. See docs/BUILDING.md.",
    );
}

function apiUrl(value) {
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    /^(127\.|localhost$)|\.localhost$/.test(url.hostname) ||
    ["0.0.0.0", "[::1]", "[::]"].includes(url.hostname)
  )
    throw new Error(
      "Use an HTTP or HTTPS API address that the phone can reach. Do not use localhost or URL credentials.",
    );
  return url.href.replace(/\/$/, "");
}

async function setup() {
  let text;
  try {
    text = await readFile(envPath, "utf8");
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    text = await readFile(join(root, ".env.example"), "utf8");
  }
  const current = parseEnv(text);
  const address = Object.values(networkInterfaces())
    .flat()
    .find(
      (item) =>
        item &&
        item.family === "IPv4" &&
        !item.internal &&
        /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(item.address),
    )?.address;
  const suggested =
    current.EXPO_PUBLIC_API_URL &&
    !/localhost|127\.0\.0\.1/.test(current.EXPO_PUBLIC_API_URL)
      ? current.EXPO_PUBLIC_API_URL
      : address
        ? `http://${address}:4310`
        : "";
  const prompt = createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  let api;
  try {
    api = apiUrl(
      (await prompt.question(`API URL [${suggested}]: `)).trim() || suggested,
    );
  } finally {
    prompt.close();
  }
  const changes = {
    EXPO_PUBLIC_API_URL: api,
    ALLOW_LOCAL_HTTP: String(new URL(api).protocol === "http:"),
    HOST: "0.0.0.0",
    PORT: new URL(api).port || current.PORT || "4310",
    SESSION_SECRET: current.SESSION_SECRET || randomBytes(32).toString("hex"),
  };
  for (const [key, value] of Object.entries(changes)) {
    const line = `${key}=${JSON.stringify(value)}`;
    const pattern = new RegExp(
      `^[ \\t]*(?:export[ \\t]+)?${key}[ \\t]*=.*$`,
      "gm",
    );
    text = pattern.test(text)
      ? text.replace(pattern, () => line)
      : `${text.trimEnd()}\n${line}\n`;
  }
  await writeFile(`${envPath}.tmp`, text, { mode: 0o600 });
  await rename(`${envPath}.tmp`, envPath);
  console.log(
    "Setup complete. Run npm run api:device. Keep that terminal open, then run a build command in another terminal.",
  );
}

async function main() {
  if (!npmCli)
    throw new Error("Use the npm scripts listed in docs/INSTALL.md.");
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (!(
    (major === 22 && minor >= 20) ||
    (major === 24 && minor >= 3) ||
    major >= 26
  ))
    throw new Error("Use Node 22.20.0. Run nvm use from the app directory.");
  if (command === "setup") {
    run(npmCli, ["ci"]);
    // Use the same parser as Expo so blank values keep their meaning.
    parseEnv = (await import("dotenv")).parse;
    return setup();
  }
  if (!["api", "android", "ios", "prepare-ios"].includes(command))
    throw new Error("Choose setup, api, android, ios, or prepare-ios.");
  try {
    parseEnv = (await import("dotenv")).parse;
    values = parseEnv(await readFile(envPath, "utf8"));
    const local = await readFile(join(root, ".env.local"), "utf8").catch(
      (error) => {
        if (error.code === "ENOENT") return "";
        throw error;
      },
    );
    Object.assign(values, parseEnv(local));
    await access(join(root, "node_modules/expo/package.json"));
  } catch (error) {
    if (["ENOENT", "ERR_MODULE_NOT_FOUND"].includes(error.code))
      throw new Error("Run npm run setup:device first.");
    throw error;
  }
  const api = apiUrl(values.EXPO_PUBLIC_API_URL);
  if (command === "api") {
    values.HOST = "0.0.0.0";
    console.log(`Open ${api}/health from the phone to check connectivity.`);
    return run(join(root, "node_modules/tsx/dist/cli.mjs"), [
      "server/index.ts",
    ]);
  }
  values.EXPO_NO_TELEMETRY = "1";
  values.EXPO_OFFLINE = "1";
  const telemetryEnabled =
    values.EXPO_PUBLIC_DD_ENABLED ?? process.env.EXPO_PUBLIC_DD_ENABLED;
  const site =
    (values.EXPO_PUBLIC_DD_SITE ?? process.env.EXPO_PUBLIC_DD_SITE) || "US1";
  if (
    telemetryEnabled === "true" &&
    !["US1", "US3", "US5", "EU1", "AP1", "AP2", "US1_FED", "US2_FED"].includes(
      site.toUpperCase(),
    )
  )
    throw new Error(
      "EXPO_PUBLIC_DD_SITE must use a native site code: US1, US3, US5, EU1, AP1, AP2, US1_FED, or US2_FED. Use US5 for us5.datadoghq.com. A hostname can send native telemetry to the wrong site.",
    );
  if (command === "android") await androidTools();
  else iosTools();
  if (command !== "prepare-ios") {
    const healthy = await fetch(`${api}/health`, {
      signal: AbortSignal.timeout(5000),
    })
      .then(
        async (response) =>
          response.ok && (await response.json()).demo === true,
      )
      .catch(() => false);
    if (!healthy)
      throw new Error(
        "The demo API health check failed. Start npm run api:device first.",
      );
  }
  const platform = command === "android" ? "android" : "ios";
  // Preserve the signing team selected in Xcode when native config is refreshed.
  expo(["prebuild", "--platform", platform, "--no-install", "--no-clean"]);
  if (platform === "android") {
    const cwd = join(root, "android");
    // Keep the Gradle daemon on the same JDK as the validated build environment.
    const javaOption = `-Dorg.gradle.java.home=${values.JAVA_HOME}`;
    // Gradle does not track Expo environment values as bundle inputs.
    const buildArgs = [
      ":app:createBundleReleaseJsAndAssets",
      "--rerun",
      "assembleRelease",
      "--console=plain",
    ];
    if (process.platform === "win32")
      runTool(
        "cmd.exe",
        [
          "/d",
          "/s",
          "/c",
          `gradlew.bat "${javaOption}" ${buildArgs.join(" ")}`,
        ],
        { cwd },
      );
    else
      runTool(join(cwd, "gradlew"), [javaOption, ...buildArgs], {
        cwd,
      });
    const artifact = join(root, "artifacts/fieldwork-one.apk");
    await mkdir(join(root, "artifacts"), { recursive: true });
    await copyFile(
      join(cwd, "app/build/outputs/apk/release/app-release.apk"),
      artifact,
    );
    console.log(
      `Demo APK: ${artifact}\nShare over Wi-Fi: npm run serve:android\nInstall over USB: adb install -r artifacts/fieldwork-one.apk`,
    );
    return;
  }
  runTool("pod", ["install"], { cwd: join(root, "ios") });
  if (command === "prepare-ios") {
    runTool("open", [join(root, "ios/FieldworkOne.xcworkspace")]);
    console.log(
      "In Xcode, select the app target and your signing team. Connect and trust the iPhone, then run npm run build:ios.",
    );
    return;
  }
  expo([
    "run:ios",
    "--device",
    "--configuration",
    "Release",
    "--no-bundler",
    "--no-install",
  ]);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});

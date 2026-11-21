import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import {
  access,
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { createServer } from "node:http";
import { networkInterfaces, tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";

const exec = promisify(execFile);
const source = fileURLToPath(new URL("../", import.meta.url));
// The helper uses Xcode tools, so these checks run only on macOS.
const skip = process.platform !== "darwin";

const phone = (name, udid, connection = {}) => ({
  identifier: `core-${udid}`,
  connectionProperties: {
    pairingState: "paired",
    tunnelState: "disconnected",
    ...connection,
  },
  deviceProperties: { name },
  hardwareProperties: { platform: "iOS", reality: "physical", udid },
});
const simulator = {
  identifier: "SIM-1",
  connectionProperties: { pairingState: "paired", tunnelState: "connected" },
  deviceProperties: { name: "Simulator iPhone" },
  hardwareProperties: { platform: "iOS", reality: "simulated", udid: "SIM-1" },
};

async function fixture(t, { devices, team = true }) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "fieldwork-ios-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, "scripts"));
  await copyFile(
    join(source, "scripts/device-demo.mjs"),
    join(root, "scripts/device-demo.mjs"),
  );
  await mkdir(join(root, "node_modules/expo/bin"), { recursive: true });
  await symlink(
    join(source, "node_modules/dotenv"),
    join(root, "node_modules/dotenv"),
    "dir",
  );
  await writeFile(join(root, "node_modules/expo/package.json"), "{}");
  await writeFile(join(root, "node_modules/expo/bin/cli"), "");
  await mkdir(join(root, "ios/FieldworkOne.xcodeproj"), { recursive: true });
  await writeFile(
    join(root, "ios/FieldworkOne.xcodeproj/project.pbxproj"),
    team
      ? "DEVELOPMENT_TEAM = ABCDE12345;\n"
      : "CODE_SIGN_STYLE = Automatic;\n",
  );

  // Each fake tool records its arguments so the test can check the sequence.
  const log = join(root, "tools.log");
  const bin = join(root, "bin");
  await mkdir(bin);
  const tool = (name, body) =>
    writeFile(
      join(bin, name),
      `#!${process.execPath}
const fs = require("node:fs");
const args = process.argv.slice(2);
fs.appendFileSync(${JSON.stringify(log)}, JSON.stringify([${JSON.stringify(name)}, ...args]) + "\\n");
${body}`,
      { mode: 0o755 },
    );
  await tool("pod", "");
  await tool(
    "xcodebuild",
    `if (args[0] === "-version") process.exit(0);
const app = "ios/build/Build/Products/Release-iphoneos/FieldworkOne.app";
fs.mkdirSync(app, { recursive: true });
fs.writeFileSync(app + "/Info.plist", '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>ai.oodle.fieldworkdemo</string></dict></plist>');`,
  );
  await tool(
    "xcrun",
    `if (args[1] === "list")
  console.log(JSON.stringify({ result: { devices: ${JSON.stringify(devices)} } }));`,
  );

  const address = Object.values(networkInterfaces())
    .flat()
    .find((item) => item?.family === "IPv4" && !item.internal)?.address;
  assert.ok(address, "The build check needs a local network interface.");
  const api = createServer((request, response) =>
    response.end('{"demo":true}'),
  );
  await new Promise((resolve) => api.listen(0, address, resolve));
  t.after(() => new Promise((resolve) => api.close(resolve)));
  await writeFile(
    join(root, ".env"),
    `EXPO_PUBLIC_API_URL=http://${address}:${api.address().port}\n`,
  );

  const run = (...args) =>
    exec(
      process.execPath,
      [join(root, "scripts/device-demo.mjs"), "install-ios", ...args],
      {
        cwd: root,
        env: {
          ...process.env,
          npm_execpath: "fixture-npm",
          PATH: `${bin}:${process.env.PATH}`,
        },
        timeout: 10000,
      },
    );
  const calls = async () =>
    (await readFile(log, "utf8").catch(() => ""))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  return { root, run, calls };
}

const built = (calls) =>
  calls.some(([name, first]) => name === "xcodebuild" && first !== "-version");

test(
  "install:ios builds for the connected iPhone, then installs and opens the app",
  { skip },
  async (t) => {
    const { root, run, calls } = await fixture(t, {
      devices: [simulator, phone("Field iPhone", "00008130-000A")],
    });

    const result = await run();
    const log = await calls();
    const build = log.find(
      ([name, first]) => name === "xcodebuild" && first !== "-version",
    );
    const artifact = join(root, "artifacts/fieldwork-one.app");

    assert.ok(build.includes("id=00008130-000A"));
    assert.ok(build.includes("-allowProvisioningDeviceRegistration"));
    assert.ok(build.includes("Release"));
    await access(join(artifact, "Info.plist"));
    assert.deepEqual(
      log.find(
        ([name, , , action]) => name === "xcrun" && action === "install",
      ),
      [
        "xcrun",
        "devicectl",
        "device",
        "install",
        "app",
        "--device",
        "00008130-000A",
        artifact,
      ],
    );
    assert.deepEqual(log.at(-1).slice(-3), [
      "--device",
      "00008130-000A",
      "ai.oodle.fieldworkdemo",
    ]);
    assert.match(
      result.stdout,
      /Installed and opened Fieldwork One on Field iPhone/,
    );
  },
);

test(
  "install:ios stops before the build when no iPhone is connected",
  { skip },
  async (t) => {
    const { run, calls } = await fixture(t, {
      devices: [
        simulator,
        phone("Old iPhone", "00008130-000B", { tunnelState: "unavailable" }),
      ],
    });

    await assert.rejects(run(), (error) => {
      assert.match(error.stderr, /Connect and trust an iPhone/);
      return true;
    });
    assert.equal(built(await calls()), false);
  },
);

test(
  "install:ios asks for --device when more than one iPhone is available",
  { skip },
  async (t) => {
    const devices = [
      phone("Field iPhone A", "00008130-000A"),
      phone("Field iPhone B", "00008130-000B"),
    ];
    const first = await fixture(t, { devices });
    await assert.rejects(first.run(), (error) => {
      assert.match(error.stderr, /Field iPhone A, Field iPhone B/);
      assert.match(error.stderr, /--device "NAME"/);
      return true;
    });

    const second = await fixture(t, { devices });
    await second.run("--device", "field iphone b");
    const build = (await second.calls()).find(
      ([name, first]) => name === "xcodebuild" && first !== "-version",
    );
    assert.ok(build.includes("id=00008130-000B"));
  },
);

test(
  "install:ios stops before the build without a signing team",
  { skip },
  async (t) => {
    const { run, calls } = await fixture(t, {
      devices: [phone("Field iPhone", "00008130-000A")],
      team: false,
    });

    await assert.rejects(run(), (error) => {
      assert.match(error.stderr, /Select a signing team/);
      return true;
    });
    assert.equal(built(await calls()), false);
  },
);

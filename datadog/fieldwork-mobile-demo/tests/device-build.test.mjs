import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import {
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
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

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), "fieldwork-build-"));
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
  await mkdir(join(root, "sdk"));
  const jdk25 = join(root, "Android Studio JDK 25");
  const jdk27 = join(root, "JDK 27");
  for (const [home, version] of [
    [jdk25, "25"],
    [jdk27, "27"],
  ]) {
    await mkdir(join(home, "bin"), { recursive: true });
    await writeFile(
      join(home, "bin/java"),
      `#!${process.execPath}\nconsole.error(${JSON.stringify(`java.home = ${home}\njava.specification.version = ${version}`)});`,
      { mode: 0o755 },
    );
    await writeFile(
      join(home, "bin/javac"),
      `#!${process.execPath}\nprocess.exit(0);`,
      { mode: 0o755 },
    );
  }
  await writeFile(
    join(root, ".env"),
    "EXPO_PUBLIC_API_URL=http://192.0.2.1:4310\n",
  );
  const run = () =>
    exec(process.execPath, [join(root, "scripts/device-demo.mjs"), "android"], {
      cwd: root,
      env: {
        ...process.env,
        npm_execpath: "fixture-npm",
        JAVA_HOME: jdk27,
        ANDROID_HOME: join(root, "sdk"),
      },
      timeout: 10000,
    });
  return { root, jdk25, run };
}

test("the native build rejects a Datadog hostname before compilation", async (t) => {
  const { root, run } = await fixture(t);
  await writeFile(
    join(root, ".env.local"),
    "EXPO_PUBLIC_DD_ENABLED=true\nEXPO_PUBLIC_DD_SITE=us5.datadoghq.com\n",
  );

  await assert.rejects(run(), (error) => {
    assert.equal(error.code, 1);
    assert.match(
      error.stderr,
      /EXPO_PUBLIC_DD_SITE must use a native site code/,
    );
    assert.match(error.stderr, /Use US5 for us5.datadoghq.com/);
    return true;
  });
});

test(
  "the Android build rejects Java 27 before native compilation",
  { skip: process.platform === "win32" },
  async (t) => {
    const { run } = await fixture(t);

    await assert.rejects(run(), (error) => {
      assert.equal(error.code, 1);
      assert.match(error.stderr, /JAVA_HOME selects Java 27/);
      assert.match(error.stderr, /Java 17 through 26/);
      return true;
    });
  },
);

test(
  "a local Java 25 override selects the Gradle runtime when the shell uses Java 27",
  { skip: process.platform === "win32" },
  async (t) => {
    const { root, jdk25, run } = await fixture(t);
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
    await writeFile(
      join(root, ".env.local"),
      `JAVA_HOME=${JSON.stringify(jdk25)}\nEXPO_PUBLIC_DD_ENABLED=true\nEXPO_PUBLIC_DD_SITE=US5\n`,
    );
    await mkdir(join(root, "android"));
    await writeFile(
      join(root, "android/gradlew"),
      `#!${process.execPath}
const fs = require('node:fs');
const bundleTask = process.argv.indexOf(':app:createBundleReleaseJsAndAssets');
if (bundleTask < 0 || process.argv[bundleTask + 1] !== '--rerun') {
  console.error('The build must refresh the bundle to include environment changes.');
  process.exit(1);
}
const artifact = { javaHome: process.env.JAVA_HOME, daemonHome: process.argv.find(value => value.startsWith('-Dorg.gradle.java.home='))?.split('=').slice(1).join('=') };
fs.mkdirSync('app/build/outputs/apk/release', {recursive:true});
fs.writeFileSync('app/build/outputs/apk/release/app-release.apk', JSON.stringify(artifact));
`,
      { mode: 0o755 },
    );

    const result = await run();
    const artifact = JSON.parse(
      await readFile(join(root, "artifacts/fieldwork-one.apk"), "utf8"),
    );

    assert.match(result.stdout, /Android build: Java 25/);
    assert.deepEqual(artifact, { javaHome: jdk25, daemonHome: jdk25 });
  },
);

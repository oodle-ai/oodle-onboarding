import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { createInstallServer } from "../scripts/install-android.mjs";

async function installer(t) {
  const directory = await mkdtemp(join(tmpdir(), "fieldwork-install-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  await mkdir(join(directory, "artifacts"));
  const apkPath = join(directory, "artifacts/fieldwork-one.apk");
  const apk = Buffer.from("Synthetic APK download fixture\0\xff", "latin1");
  await writeFile(apkPath, apk);
  const server = await createInstallServer({
    apkPath,
    url: "http://192.168.1.10:4311/",
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const url = `http://127.0.0.1:${server.address().port}`;
  return { apk, apkPath, directory, url };
}

test("the install page provides a QR image and an APK download", async (t) => {
  const { url } = await installer(t);

  const page = await fetch(url);
  const html = await page.text();
  const qr = await fetch(new URL("/qr.svg", url));

  assert.equal(page.status, 200);
  assert.match(html, /href="\/fieldwork-one\.apk"/);
  assert.match(html, /src="\/qr\.svg"/);
  assert.equal(qr.status, 200);
  assert.equal(qr.headers.get("content-type"), "image/svg+xml");
  assert.match(await qr.text(), /<svg/);
});

test("the APK download preserves the file bytes and install metadata", async (t) => {
  const { apk, url } = await installer(t);

  const response = await fetch(new URL("/fieldwork-one.apk", url));
  const body = Buffer.from(await response.arrayBuffer());
  const head = await fetch(new URL("/fieldwork-one.apk", url), {
    method: "HEAD",
  });

  assert.equal(response.status, 200);
  assert.equal(
    response.headers.get("content-type"),
    "application/vnd.android.package-archive",
  );
  assert.equal(
    response.headers.get("content-disposition"),
    'attachment; filename="fieldwork-one.apk"',
  );
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(body, apk);
  assert.equal(head.status, 200);
  assert.equal(head.headers.get("content-length"), String(apk.length));
  assert.equal(await head.text(), "");
});

test("the server does not expose credentials or other files", async (t) => {
  const { directory, url } = await installer(t);
  await writeFile(join(directory, ".env"), "SESSION_SECRET=private-fixture");
  await writeFile(join(directory, "artifacts/other.txt"), "private-fixture");

  const env = await fetch(new URL("/.env", url));
  const traversal = await fetch(`${url}/%2e%2e%2f.env`);
  const artifact = await fetch(new URL("/other.txt", url));
  const listing = await fetch(new URL("/artifacts/", url));
  const upload = await fetch(new URL("/fieldwork-one.apk", url), {
    method: "POST",
    body: "replace",
  });

  assert.equal(env.status, 404);
  assert.equal(traversal.status, 404);
  assert.equal(artifact.status, 404);
  assert.equal(listing.status, 404);
  assert.equal(upload.status, 405);
  assert.equal(await env.text(), "Not found.");
});

test("a removed APK gives a useful error without stopping the server", async (t) => {
  const { apkPath, url } = await installer(t);
  await rm(apkPath);

  const response = await fetch(new URL("/fieldwork-one.apk", url));
  const page = await fetch(url);

  assert.equal(response.status, 503);
  assert.match(await response.text(), /npm run build:android/);
  assert.equal(page.status, 200);
});

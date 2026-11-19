import { open, readFile, realpath } from "node:fs/promises";
import { createServer } from "node:http";
import { networkInterfaces } from "node:os";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { parse } from "dotenv";
import QRCode from "qrcode";

const root = fileURLToPath(new URL("../", import.meta.url));
const apkName = "fieldwork-one.apk";

async function openApk(apkPath) {
  const file = await open(apkPath, "r");
  const info = await file.stat();
  if (!info.isFile() || info.size === 0) {
    await file.close();
    throw new Error(
      "The APK is empty or is not a file. Run npm run build:android.",
    );
  }
  return { file, info };
}

export async function createInstallServer({ apkPath, url }) {
  const { file } = await openApk(apkPath);
  await file.close();
  const page = await readFile(
    new URL("./install-android.html", import.meta.url),
  );
  const qr = await QRCode.toString(url, { type: "svg", margin: 4, width: 280 });

  return createServer(async (request, response) => {
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("X-Content-Type-Options", "nosniff");
    response.setHeader("Referrer-Policy", "no-referrer");
    response.setHeader(
      "Content-Security-Policy",
      "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    );
    const send = (status, type, body) => {
      response.writeHead(status, { "Content-Type": type });
      response.end(request.method === "HEAD" ? undefined : body);
    };
    if (!["GET", "HEAD"].includes(request.method)) {
      response.setHeader("Allow", "GET, HEAD");
      return send(405, "text/plain", "Use GET or HEAD.");
    }
    try {
      // Serve fixed routes so source files and credentials cannot be downloaded.
      const path = new URL(request.url, "http://localhost").pathname;
      if (path === "/") return send(200, "text/html; charset=utf-8", page);
      if (path === "/qr.svg") return send(200, "image/svg+xml", qr);
      if (path !== `/${apkName}`) return send(404, "text/plain", "Not found.");

      const { file, info } = await openApk(apkPath);
      response.writeHead(200, {
        "Content-Type": "application/vnd.android.package-archive",
        "Content-Disposition": `attachment; filename="${apkName}"`,
        "Content-Length": info.size,
      });
      if (request.method === "HEAD") {
        await file.close();
        return response.end();
      }
      await pipeline(file.createReadStream(), response);
    } catch {
      if (response.headersSent) response.destroy();
      else
        send(
          503,
          "text/plain",
          "The APK is unavailable. Run npm run build:android and restart this server.",
        );
    }
  });
}

async function main() {
  const { values } = parseArgs({
    options: {
      host: { type: "string" },
      port: { type: "string", default: "4311" },
      help: { type: "boolean", short: "h" },
    },
  });
  if (values.help) {
    console.log("npm run serve:android -- [--host YOUR_LAN_IP] [--port 4311]");
    return;
  }
  const port = Number(values.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("Use a port from 1 to 65535.");
  const addresses = Object.values(networkInterfaces())
    .flat()
    .filter((item) => item?.family === "IPv4" && !item.internal)
    .map((item) => item.address);
  let apiHost;
  try {
    const env = parse(await readFile(join(root, ".env"), "utf8"));
    apiHost = new URL(env.EXPO_PUBLIC_API_URL).hostname;
  } catch {
    // An existing APK can be shared without the build environment.
  }
  const host =
    values.host ||
    (addresses.includes(apiHost)
      ? apiHost
      : addresses.find((address) =>
          /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(address),
        ));
  if (!host || !addresses.includes(host))
    throw new Error(
      "Connect to Wi-Fi, then use --host with this computer's LAN IPv4 address.",
    );

  const url = `http://${host}:${port}/`;
  let server;
  try {
    server = await createInstallServer({
      apkPath: join(root, "artifacts", apkName),
      url,
    });
  } catch (error) {
    if (error.code === "ENOENT")
      throw new Error("No APK found. Run npm run build:android first.");
    throw error;
  }
  const terminalQr = await QRCode.toString(url, {
    type: "terminal",
    small: true,
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, resolve);
  });
  console.log(`\nScan with your Android camera:\n${terminalQr}`);
  console.log(`Install page: ${url}`);
  console.log(
    "Use the same Wi-Fi on both devices. Tap Download APK, then install it.",
  );
  console.log(
    "Keep the API running in its own terminal. Press Ctrl+C to stop sharing.",
  );
  const stop = () => {
    server.close();
    server.closeAllConnections();
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
}

if (
  process.argv[1] &&
  (await realpath(process.argv[1])) === fileURLToPath(import.meta.url)
) {
  main().catch((error) => {
    console.error(
      error.code === "EADDRINUSE"
        ? "Port is in use. Retry with npm run serve:android -- --port 4312."
        : error.message,
    );
    process.exitCode = 1;
  });
}

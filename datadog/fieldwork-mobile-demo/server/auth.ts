import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { User } from "../src/shared/model";

const secret = process.env.SESSION_SECRET || randomBytes(32).toString("hex");
const sign = (payload: string) =>
  createHmac("sha256", secret).update(payload).digest("base64url");
export function issueToken(user: User) {
  const payload = Buffer.from(
    JSON.stringify({ sub: user.id, exp: Date.now() + 24 * 60 * 60 * 1000 }),
  ).toString("base64url");
  return `${payload}.${sign(payload)}`;
}
export function readToken(token?: string): string | undefined {
  if (!token || token.length > 2000) return;
  const [payload, signature] = token.split(".");
  if (!payload || !signature) return;
  const expected = Buffer.from(sign(payload));
  const actual = Buffer.from(signature);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual))
    return;
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString());
    return data.exp > Date.now() && typeof data.sub === "string"
      ? data.sub
      : undefined;
  } catch {
    return;
  }
}

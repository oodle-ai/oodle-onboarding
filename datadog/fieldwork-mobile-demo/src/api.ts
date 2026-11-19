import { createTRPCClient, httpLink } from "@trpc/client";
import type { AppRouter } from "../server/router";
import { apiUrl } from "./config";

export async function timedFetch(input: RequestInfo | URL, init?: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
export const client = (token: string) =>
  createTRPCClient<AppRouter>({
    links: [
      httpLink({
        url: `${apiUrl}/api/trpc`,
        headers: { Authorization: `Bearer ${token}` },
        fetch: timedFetch,
      }),
    ],
  });
export async function authPost<T>(path: string, body: unknown): Promise<T> {
  const response = await timedFetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error || "The request failed. Try again.");
  return result as T;
}

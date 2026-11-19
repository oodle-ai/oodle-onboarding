import React, {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { AppState } from "react-native";
import * as Crypto from "expo-crypto";
import { TRPCClientError } from "@trpc/client";
import { authPost, client } from "./api";
import { credentials, storage } from "./storage";
import { Command, Envelope, Snapshot, User } from "./shared/model";
import { telemetry } from "./telemetry";

type Session = { token: string; user: User };
export type QueuedAction = Envelope & { error?: string; createdAt: string };
type Toast = { message: string; tone: "success" | "error" | "info" };
type AppContext = {
  booting: boolean;
  session: Session | null;
  data: Snapshot | null;
  offline: boolean;
  setOffline(value: boolean): void;
  queue: QueuedAction[];
  sync: "online" | "offline" | "syncing";
  telemetryStatus: string;
  consent: boolean;
  login(profile: string): Promise<void>;
  loginOtp(challengeId: string, code: string): Promise<void>;
  logout(): Promise<void>;
  refresh(): Promise<void>;
  run(command: Command): Promise<{ entityId?: string; queued: boolean }>;
  flush(): Promise<void>;
  discard(requestId: string): Promise<void>;
  setConsent(value: boolean): Promise<void>;
  replay: boolean;
  setReplay(value: boolean): Promise<void>;
  toast: Toast | null;
  notify(message: string, tone?: Toast["tone"]): void;
  office: boolean;
  workspace: "field" | "office";
  setWorkspace(value: "field" | "office"): void;
};
const Context = createContext<AppContext | null>(null);
const queueKey = (id: string) => `fieldwork-queue:${id}`;
const snapshotKey = (id: string) => `fieldwork-snapshot:${id}`;
const apiError = (error: unknown) =>
  error instanceof TRPCClientError
    ? (error.data?.code as string | undefined)
    : undefined;
const isRetryable = (error: unknown) =>
  !apiError(error) ||
  ["TIMEOUT", "INTERNAL_SERVER_ERROR", "SERVICE_UNAVAILABLE"].includes(
    apiError(error)!,
  );

export function AppProvider({ children }: PropsWithChildren) {
  const [booting, setBooting] = useState(true);
  const [session, setSession] = useState<Session | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const [data, setData] = useState<Snapshot | null>(null);
  const [offline, setOffline] = useState(false);
  const offlineRef = useRef(false);
  offlineRef.current = offline;
  const [queue, setQueue] = useState<QueuedAction[]>([]);
  const queueRef = useRef<QueuedAction[]>([]);
  const flushing = useRef(false);
  const queueWrites = useRef(Promise.resolve());
  const [sync, setSync] = useState<AppContext["sync"]>("online");
  const [consent, updateConsent] = useState(true);
  const [replay, updateReplay] = useState(true);
  const [telemetryStatus, setTelemetryStatus] = useState("Starting");
  const [toast, setToast] = useState<Toast | null>(null);
  const [workspace, setWorkspace] = useState<"field" | "office">("field");
  const notify = useCallback(
    (message: string, tone: Toast["tone"] = "info") =>
      setToast({ message, tone }),
    [],
  );
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5500);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const saveQueue = useCallback(
    async (value: QueuedAction[], owner: Session) => {
      if (sessionRef.current === owner) {
        queueRef.current = value;
        setQueue(value);
      }
      const write = queueWrites.current.then(() =>
        storage.setItem(queueKey(owner.user.id), JSON.stringify(value)),
      );
      queueWrites.current = write.catch(() => undefined);
      await write;
    },
    [],
  );

  const refresh = useCallback(async () => {
    const current = sessionRef.current;
    if (!current || offlineRef.current) {
      if (current) setSync("offline");
      return;
    }
    try {
      const result = await client(current.token).sync.snapshot.query();
      if (sessionRef.current !== current) return;
      setData(result);
      setSync("online");
      await storage
        .setItem(snapshotKey(current.user.id), JSON.stringify(result))
        .catch(() => {
          if (sessionRef.current === current)
            notify(
              "Workspace loaded, but could not be saved for offline use.",
              "error",
            );
        });
      telemetry.ready();
    } catch (error) {
      if (sessionRef.current !== current) return;
      setSync("offline");
      if (apiError(error) === "UNAUTHORIZED")
        notify(
          "Your session expired. Sign in again. Queued actions remain on this device.",
          "error",
        );
    }
  }, [notify]);

  const activate = useCallback(
    async (next: Session) => {
      await credentials.set(JSON.stringify(next));
      await telemetry.user(next.user).catch(() => undefined);
      sessionRef.current = next;
      setSession(next);
      setData(null);
      setWorkspace(next.user.role === "driver" ? "field" : "office");
      const [cached, pending] = await Promise.all([
        storage.getItem(snapshotKey(next.user.id)),
        storage.getItem(queueKey(next.user.id)),
      ]);
      if (sessionRef.current !== next) return;
      if (cached) setData(JSON.parse(cached));
      const actions: QueuedAction[] = pending ? JSON.parse(pending) : [];
      queueRef.current = actions;
      setQueue(actions);
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    void (async () => {
      const allowed = (await storage.getItem("fieldwork-consent")) !== "false";
      updateConsent(allowed);
      try {
        setTelemetryStatus(await telemetry.initialize(allowed));
      } catch (error) {
        setTelemetryStatus("SDK initialization failed");
        console.warn(
          "Datadog initialization failed:",
          error instanceof Error ? error.message : String(error),
        );
      }
      const saved = await credentials.get();
      if (saved) await activate(JSON.parse(saved));
    })()
      .catch((error) =>
        notify(
          error instanceof Error
            ? error.message
            : "The app could not restore this session.",
          "error",
        ),
      )
      .finally(() => setBooting(false));
  }, [activate, notify]);

  const flush = useCallback(async () => {
    const current = sessionRef.current;
    if (!current || offlineRef.current || flushing.current) return;
    flushing.current = true;
    setSync("syncing");
    try {
      while (
        sessionRef.current === current &&
        queueRef.current.length &&
        !offlineRef.current
      ) {
        const item = queueRef.current[0]!;
        try {
          await client(current.token).workflow.execute.mutate({
            requestId: item.requestId,
            command: item.command,
          });
          if (sessionRef.current !== current) return;
          await saveQueue(
            queueRef.current.filter((q) => q.requestId !== item.requestId),
            current,
          );
          telemetry.action("Offline action synchronized", {
            operation: item.command.type,
          });
        } catch (error) {
          if (sessionRef.current !== current) return;
          if (!isRetryable(error))
            await saveQueue(
              queueRef.current.map((q) =>
                q.requestId === item.requestId
                  ? {
                      ...q,
                      error:
                        error instanceof Error
                          ? error.message
                          : "This action needs review.",
                    }
                  : q,
              ),
              current,
            );
          setSync("offline");
          break;
        }
      }
      await refresh();
    } finally {
      flushing.current = false;
    }
  }, [refresh, saveQueue]);

  useEffect(() => {
    if (!session || offline) return;
    void flush();
    const timer = setInterval(() => {
      if (AppState.currentState === "active") void flush();
    }, 10000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void flush();
    });
    return () => {
      clearInterval(timer);
      subscription.remove();
    };
  }, [session, offline, flush]);

  const run = useCallback(
    async (command: Command) => {
      const current = sessionRef.current;
      if (!current) throw new Error("Sign in to continue.");
      const envelope = { requestId: Crypto.randomUUID(), command };
      telemetry.action("Workflow submitted", {
        operation: command.type,
        business_role: current.user.role,
      });
      let result: { entityId: string; duplicate: boolean } | undefined;
      try {
        if (offlineRef.current || queueRef.current.length)
          throw new Error("The action will wait for synchronization.");
        result = await telemetry.operation(
          command.type,
          envelope.requestId,
          () => client(current.token).workflow.execute.mutate(envelope),
        );
      } catch (error) {
        if (!isRetryable(error)) {
          telemetry.error(error, { operation: command.type });
          throw error;
        }
        if (sessionRef.current !== current)
          throw new Error(
            "The profile changed before this action could be saved.",
          );
        if (queueRef.current.length >= 50)
          throw new Error(
            "Synchronize the pending actions before you add more.",
          );
        await saveQueue(
          [
            ...queueRef.current,
            { ...envelope, createdAt: new Date().toISOString() },
          ],
          current,
        );
        setSync("offline");
        notify(
          "Saved on this device. The server will validate this action when you reconnect.",
          "info",
        );
        return { queued: true };
      }
      telemetry.action("Workflow completed", {
        operation: command.type,
        entity_id: result.entityId,
      });
      await refresh();
      return { ...result, queued: false };
    },
    [notify, refresh, saveQueue],
  );

  return (
    <Context.Provider
      value={{
        booting,
        session,
        data,
        offline,
        setOffline: (value) => {
          offlineRef.current = value;
          setOffline(value);
          if (value) setSync("offline");
        },
        queue,
        sync,
        telemetryStatus,
        consent,
        toast,
        notify,
        office: session?.user.role !== "driver",
        workspace,
        setWorkspace,
        login: async (profile) =>
          activate(
            await authPost<Session>("/api/auth/login", {
              profile,
              code: "demo",
            }),
          ),
        loginOtp: async (challengeId, code) =>
          activate(
            await authPost<Session>("/api/auth/otp/verify", {
              challengeId,
              code,
            }),
          ),
        logout: async () => {
          sessionRef.current = null;
          setSession(null);
          setData(null);
          queueRef.current = [];
          setQueue([]);
          await credentials.clear();
          await telemetry.user().catch(() => undefined);
        },
        refresh,
        run,
        flush,
        discard: async (id) => {
          if (sessionRef.current)
            await saveQueue(
              queueRef.current.filter((q) => q.requestId !== id),
              sessionRef.current,
            );
        },
        setConsent: async (allowed) => {
          await telemetry.consent(allowed);
          await storage.setItem("fieldwork-consent", String(allowed));
          updateConsent(allowed);
          notify(
            allowed
              ? "Telemetry collection is enabled when credentials are configured."
              : "Telemetry collection is paused.",
          );
        },
        replay,
        setReplay: async (record) => {
          await telemetry.replay(record);
          updateReplay(record);
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error("AppProvider is required.");
  return value;
}

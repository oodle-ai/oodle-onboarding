import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { Pool } from "pg";
import { State } from "../src/shared/model";
import { seedState } from "./seed";

export interface Store {
  read(): Promise<State>;
  transaction<T>(operation: (state: State) => T | Promise<T>): Promise<T>;
  close(): Promise<void>;
}

export class FileStore implements Store {
  private tail: Promise<unknown> = Promise.resolve();
  constructor(private path: string) {}
  async read(): Promise<State> {
    await this.tail;
    return this.load();
  }
  private async load(): Promise<State> {
    try {
      return JSON.parse(await readFile(this.path, "utf8"));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      return seedState();
    }
  }
  transaction<T>(operation: (state: State) => T | Promise<T>): Promise<T> {
    const next = this.tail.then(async () => {
      const state = await this.load();
      const result = await operation(state);
      await mkdir(dirname(this.path), { recursive: true });
      await writeFile(`${this.path}.tmp`, JSON.stringify(state), {
        mode: 0o600,
      });
      await rename(`${this.path}.tmp`, this.path);
      return result;
    });
    this.tail = next.catch(() => undefined);
    return next;
  }
  async close() {
    await this.tail;
  }
}

export class PostgresStore implements Store {
  private pool: Pool;
  private ready: Promise<void>;
  constructor(connectionString: string) {
    this.pool = new Pool({ connectionString, max: 5 });
    this.ready = this.initialize();
  }
  private async initialize() {
    await this.pool.query(
      "CREATE TABLE IF NOT EXISTS fieldwork_demo (id integer PRIMARY KEY, state jsonb NOT NULL)",
    );
    await this.pool.query(
      "INSERT INTO fieldwork_demo (id, state) VALUES (1, $1) ON CONFLICT (id) DO NOTHING",
      [JSON.stringify(seedState())],
    );
  }
  async read(): Promise<State> {
    await this.ready;
    return (
      await this.pool.query("SELECT state FROM fieldwork_demo WHERE id = 1")
    ).rows[0].state;
  }
  async transaction<T>(
    operation: (state: State) => T | Promise<T>,
  ): Promise<T> {
    await this.ready;
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      // The row lock keeps mobile retries and worker updates in one transaction.
      const state: State = (
        await client.query(
          "SELECT state FROM fieldwork_demo WHERE id = 1 FOR UPDATE",
        )
      ).rows[0].state;
      const result = await operation(state);
      await client.query("UPDATE fieldwork_demo SET state = $1 WHERE id = 1", [
        JSON.stringify(state),
      ]);
      await client.query("COMMIT");
      return result;
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
  }
  async close() {
    await this.pool.end();
  }
}

export function createStore(): Store {
  return process.env.DATABASE_URL
    ? new PostgresStore(process.env.DATABASE_URL)
    : new FileStore(process.env.DATA_FILE || "./data/state.json");
}

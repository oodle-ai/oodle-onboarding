import Storage from "expo-sqlite/kv-store";
import * as SecureStore from "expo-secure-store";

// SQLite can hold photo queues that exceed Android AsyncStorage row limits.
export const storage = Storage;
export const credentials = {
  get: () => SecureStore.getItemAsync("fieldwork-session"),
  set: (value: string) => SecureStore.setItemAsync("fieldwork-session", value),
  clear: () => SecureStore.deleteItemAsync("fieldwork-session"),
};

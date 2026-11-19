import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

export const storage = AsyncStorage;
export const credentials = {
  async get() {
    return Platform.OS === "web"
      ? sessionStorage.getItem("fieldwork-session")
      : SecureStore.getItemAsync("fieldwork-session");
  },
  async set(value: string) {
    if (Platform.OS === "web")
      sessionStorage.setItem("fieldwork-session", value);
    else await SecureStore.setItemAsync("fieldwork-session", value);
  },
  async clear() {
    if (Platform.OS === "web") sessionStorage.removeItem("fieldwork-session");
    else await SecureStore.deleteItemAsync("fieldwork-session");
  },
};

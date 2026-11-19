import { NavigatorScreenParams, useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";

export type TabParams = {
  Home: undefined;
  Schedule: undefined;
  Dispatch: undefined;
  Comms: undefined;
  More: undefined;
};
export type StackParams = {
  Main: NavigatorScreenParams<TabParams> | undefined;
  Order: { id: string };
  NewOrder: { customerId?: string } | undefined;
  Customers: undefined;
  Customer: { id: string };
  Invoices: undefined;
  Inspection: { vehicleId?: string } | undefined;
  Shift: undefined;
  Fleet: undefined;
  Notifications: undefined;
  Diagnostics: undefined;
  Queue: undefined;
  Search: undefined;
};
export const useNav = () =>
  useNavigation<NativeStackNavigationProp<StackParams>>();

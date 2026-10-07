import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { AppState, LogBox } from "react-native";
import { useEffect } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { ToastProvider } from "@/src/components/Toast";
import { ActivityAlertsProvider } from "@/src/components/ActivityAlerts";
import { api } from "@/src/api";

LogBox.ignoreAllLogs(true);

function ConnectionKeeper() {
  useEffect(() => {
    let checking = false;
    const ping = async () => {
      if (checking) return;
      checking = true;
      try { await api.health(); } catch {} finally { checking = false; }
    };
    void ping();
    const timer = setInterval(() => { if (AppState.currentState === "active") void ping(); }, 4 * 60 * 1000);
    const listener = AppState.addEventListener("change", (state) => { if (state === "active") void ping(); });
    return () => { clearInterval(timer); listener.remove(); };
  }, []);
  return null;
}

export default function RootLayout() {
  return (
    <ErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <QueryClientProvider client={queryClient}>
            <ToastProvider>
              <ConnectionKeeper />
              <ActivityAlertsProvider>
              <StatusBar style="dark" />
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#F9FAFB" } }} />
              </ActivityAlertsProvider>
            </ToastProvider>
          </QueryClientProvider>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}

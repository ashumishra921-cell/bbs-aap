import { useFocusEffect } from "expo-router";
import { useCallback, useRef } from "react";
import { AppState } from "react-native";

/** Refresh focused screens on resume and while open; never overlap requests. */
export function useLiveRefresh(load: () => Promise<void>, intervalMs = 10000) {
  const latest = useRef(load);
  latest.current = load;
  useFocusEffect(useCallback(() => {
    let active = true;
    let running = false;
    const refresh = async () => {
      if (!active || running || (AppState.currentState && AppState.currentState !== "active")) return;
      running = true;
      try { await latest.current(); } catch { /* Screen owns its error UI. */ }
      finally { running = false; }
    };
    void refresh();
    const timer = setInterval(refresh, intervalMs);
    const listener = AppState.addEventListener("change", state => {
      if (state === "active") void refresh();
    });
    return () => { active = false; clearInterval(timer); listener.remove(); };
  }, [intervalMs]));
}
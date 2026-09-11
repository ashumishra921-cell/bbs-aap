import { useCallback, useEffect, useState } from "react";
import { AppState } from "react-native";

import { api } from "@/src/api";

export type Badges = {
  new_tickets?: number;
  pending_payments?: number;
  open_tickets?: number;
  expiring_soon?: number | boolean;
  days_left?: number | null;
};

/** Polls /api/badges every `intervalMs` while the app is in the foreground. */
export function useBadges(intervalMs = 30000) {
  const [badges, setBadges] = useState<Badges>({});

  const refresh = useCallback(async () => {
    try {
      setBadges(await api.badges());
    } catch {}
  }, []);

  useEffect(() => {
    refresh();
    let timer: ReturnType<typeof setInterval> | null = setInterval(refresh, intervalMs);
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        refresh();
        if (!timer) timer = setInterval(refresh, intervalMs);
      } else if (timer) {
        clearInterval(timer);
        timer = null;
      }
    });
    return () => {
      if (timer) clearInterval(timer);
      sub.remove();
    };
  }, [refresh, intervalMs]);

  return { badges, refresh };
}

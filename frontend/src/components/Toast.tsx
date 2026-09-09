import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown, FadeOutDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme";

type Toast = { id: number; text: string; kind: "success" | "error" | "info" };

const ToastCtx = createContext<{ show: (text: string, kind?: Toast["kind"]) => void }>({
  show: () => {},
});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();

  const show = useCallback((text: string, kind: Toast["kind"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 2800);
  }, []);

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <View pointerEvents="none" style={[styles.host, { bottom: insets.bottom + 24 }]}>
        {toasts.map((t) => (
          <Animated.View
            key={t.id}
            entering={FadeInDown.springify().damping(18)}
            exiting={FadeOutDown}
            style={[
              styles.toast,
              {
                backgroundColor:
                  t.kind === "success" ? colors.success : t.kind === "error" ? colors.error : colors.surfaceInverse,
              },
            ]}
          >
            <Text style={styles.text} testID={`toast-${t.kind}`}>
              {t.text}
            </Text>
          </Animated.View>
        ))}
      </View>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

const styles = StyleSheet.create({
  host: {
    position: "absolute",
    left: 16,
    right: 16,
    alignItems: "center",
    gap: 8,
  },
  toast: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    maxWidth: "100%",
  },
  text: { color: "#FFFFFF", fontSize: 14, fontWeight: "600" },
});

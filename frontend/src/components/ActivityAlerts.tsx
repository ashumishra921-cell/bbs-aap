import AsyncStorage from "@react-native-async-storage/async-storage";
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { useSegments } from "expo-router";
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AppState, Pressable, Switch, Text, View } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";

import { api, ActivityItem, loadAuth } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";
import { useToast } from "./Toast";

type Kind = ActivityItem["kind"];
const AlertContext = createContext({ enabled: true, ready: false, lastAlert: "", toneState: "",
  toggle: (_value: boolean) => {}, testTone: (_kind: Kind) => {} });

export function ActivityAlertsProvider({ children }: { children: React.ReactNode }) {
  const segments = useSegments();
  const signedInScreen = segments.length > 0 && !["index", "otp"].includes(String(segments[0]));
  const complaint = useAudioPlayer(require("../../assets/sounds/complaint.wav"));
  const payment = useAudioPlayer(require("../../assets/sounds/payment.wav"));
  const complaintStatus = useAudioPlayerStatus(complaint);
  const paymentStatus = useAudioPlayerStatus(payment);
  const [enabled, setEnabled] = useState(true);
  const [ready, setReady] = useState(false);
  const [lastAlert, setLastAlert] = useState("");
  const [toneState, setToneState] = useState("");
  const uid = useRef<string | null>(null);
  const enabledRef = useRef(true);
  const playRef = useRef<(kind: Kind) => Promise<void>>(async () => {});
  const { show } = useToast();

  const play = useCallback(async (kind: Kind) => {
    const player = kind === "payment" ? payment : complaint;
    try {
      await setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: false, interruptionMode: "mixWithOthers" });
      await player.seekTo(0);
      player.play();
    } catch {
      setToneState("Tone नहीं चल सकी — volume और Test tone जाँचें");
    }
  }, [complaint, payment]);
  playRef.current = play;

  useEffect(() => {
    if (complaintStatus.playing) setToneState("Complaint tone playing");
    if (paymentStatus.playing) setToneState("Payment tone playing");
  }, [complaintStatus.playing, paymentStatus.playing]);

  useEffect(() => {
    let cancelled = false;
    let busy = false;
    let previous: Record<string, string> | null = null;
    setReady(false);
    setLastAlert("");
    setToneState("");
    uid.current = null;
    if (!signedInScreen) return;
    const poll = async () => {
      if (busy || cancelled || (AppState.currentState && AppState.currentState !== "active")) return;
      busy = true;
      try {
        if (!uid.current) {
          const { user } = await loadAuth();
          if (!user || cancelled) return;
          const saved = await AsyncStorage.getItem(`alert-sound:${user.id}`);
          if (cancelled) return;
          uid.current = user.id;
          enabledRef.current = saved !== "off";
          setEnabled(enabledRef.current);
          setReady(true);
        }
        const items = await api.activity();
        if (cancelled || (AppState.currentState && AppState.currentState !== "active")) return;
        const changed = previous ? items.filter(item => previous![item.key] !== item.version) : [];
        previous = Object.fromEntries(items.map(item => [item.key, item.version]));
        // First successful snapshot is silent. Comparing IDs/versions (not counts)
        // detects a new payment even if an older one was approved simultaneously.
        if (changed.length) {
          const newest = changed.find(item => item.kind === "payment") || changed[0];
          setLastAlert(newest.title);
          show(newest.title, "info");
          if (enabledRef.current) await playRef.current(newest.kind);
        }
      } catch { /* Keep the baseline on transient network errors. */ }
      finally { busy = false; }
    };
    void poll();
    const timer = setInterval(poll, 10000);
    const listener = AppState.addEventListener("change", state => {
      if (state === "active") void poll();
      else { complaint.pause(); payment.pause(); }
    });
    return () => { cancelled = true; clearInterval(timer); listener.remove(); complaint.pause(); payment.pause(); };
  }, [signedInScreen, show, complaint, payment]);

  const toggle = async (value: boolean) => {
    if (!uid.current) return;
    enabledRef.current = value;
    setEnabled(value);
    if (!value) { complaint.pause(); payment.pause(); }
    try { await AsyncStorage.setItem(`alert-sound:${uid.current}`, value ? "on" : "off"); }
    catch { show("Sound preference save नहीं हुई", "error"); }
  };
  const testTone = (kind: Kind) => {
    if (!enabledRef.current) return;
    setToneState("Tone तैयार हो रही है…");
    void play(kind);
  };
  return <AlertContext.Provider value={{ enabled, ready, lastAlert, toneState, toggle, testTone }}>{children}</AlertContext.Provider>;
}

export function AlertSoundControl() {
  const { enabled, ready, lastAlert, toneState, toggle, testTone } = useContext(AlertContext);
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <View style={styles.card} testID="sound-alert-card">
      <View style={styles.row}>
        <Ionicons name={enabled ? "notifications" : "notifications-off-outline"} size={20} color={colors.brandPrimary} />
        <Text style={styles.title} testID="sound-alert-title">Sound alerts</Text>
        <Text style={styles.hint} testID="sound-alert-state">{enabled ? "ON" : "OFF"}</Text>
        <Switch testID="sound-alert-toggle" accessibilityLabel="Sound alerts" accessibilityRole="switch" accessibilityState={{ checked: enabled, disabled: !ready }} value={enabled} disabled={!ready} onValueChange={toggle} trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }} />
      </View>
      <Text style={styles.hint} testID="sound-alert-scope">App खुली होने पर complaint और payment updates की tone (लगभग 10 सेकंड में)।</Text>
      <View style={styles.row}>
        {(["complaint", "payment"] as const).map(kind => (
          <Pressable key={kind} testID={`test-${kind}-tone`} disabled={!enabled || !ready} onPress={() => testTone(kind)} style={({ pressed }) => [styles.test, { opacity: !enabled ? 0.4 : pressed ? 0.65 : 1 }]}>
            <Ionicons name="volume-high-outline" size={16} color={colors.brandPrimary} />
            <Text style={styles.testText}>{kind === "complaint" ? "Complaint tone" : "Payment tone"}</Text>
          </Pressable>
        ))}
      </View>
      {!!toneState && <Text style={styles.hint} testID="sound-playback-status">{toneState}</Text>}
      {!!lastAlert && <Text style={styles.latest} testID="latest-activity-alert">{lastAlert}</Text>}
    </View>
  );
}

const useStyles = makeStyles(colors => ({
  card: { padding: 16, gap: 10, borderRadius: 16, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, marginTop: 16 },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  title: { flex: 1, color: colors.onSurface, fontWeight: "700", fontSize: 16 },
  hint: { color: colors.muted, fontSize: 12, lineHeight: 19 },
  test: { flex: 1, minHeight: 44, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, borderRadius: 10, padding: 6 },
  testText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 12, flexShrink: 1 },
  latest: { color: colors.brandPrimary, fontSize: 13, lineHeight: 20 },
}));
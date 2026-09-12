import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Location from "expo-location";
import dayjs from "dayjs";

import { api, clearAuth, loadAuth, User } from "@/src/api";
import HelplineCard from "@/src/components/HelplineCard";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";
import { getCurrentLocation, openAppSettings } from "@/src/utils/location";
import { AlertSoundControl } from "@/src/components/ActivityAlerts";

export default function TeamProfile() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<User | null>(null);
  const [sharing, setSharing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [lastSent, setLastSent] = useState<Date | null>(null);
  const watcher = useRef<Location.LocationSubscription | null>(null);

  useEffect(() => {
    (async () => {
      const { user } = await loadAuth();
      setUser(user);
      try {
        const me = await api.me();
        setUser(me);
        if (me.location?.sharing && me.location.updated_at) {
          setLastSent(new Date(me.location.updated_at));
        }
      } catch {}
    })();
    return () => { watcher.current?.remove(); };
  }, []);

  const push = useCallback(async (lat: number, lng: number) => {
    try {
      await api.updateMyLocation(lat, lng);
      setLastSent(new Date());
    } catch {}
  }, []);

  const startSharing = async () => {
    setBusy(true);
    const res = await getCurrentLocation();
    if (!res.ok) {
      setBusy(false);
      if (res.reason === "blocked") setBlocked(true);
      else toast.show(res.reason === "denied" ? "Location की अनुमति नहीं मिली" : "Location उपलब्ध नहीं", "error");
      return;
    }
    setBlocked(false);
    await push(res.lat, res.lng);
    try {
      watcher.current = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.Balanced, timeInterval: 60000, distanceInterval: 150 },
        (pos) => push(pos.coords.latitude, pos.coords.longitude),
      );
    } catch {}
    setSharing(true);
    setBusy(false);
    toast.show("Live location share हो रही है ✓", "success");
  };

  const stopSharing = async () => {
    watcher.current?.remove();
    watcher.current = null;
    setSharing(false);
    try { await api.stopMyLocation(); } catch {}
    toast.show("Location sharing बंद", "info");
  };

  const logout = async () => {
    watcher.current?.remove();
    await clearAuth();
    router.replace("/");
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingBottom: 32 }}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <View style={styles.avatar}>
          <Ionicons name="construct" size={34} color="#FFFFFF" />
        </View>
        <Text style={styles.name} testID="profile-name">{user?.name}</Text>
        <Text style={styles.phone}>+91 {user?.phone}</Text>
        <View style={styles.roleBadge}>
          <Text style={styles.roleText}>{user?.role?.replace("_", " ").toUpperCase()}</Text>
        </View>
      </View>

      <View style={{ padding: 16 }}>
        <View style={styles.card} testID="location-card">
          <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
            <View style={[styles.icon, { backgroundColor: sharing ? colors.success : colors.brandTertiary }]}>
              <Ionicons name="navigate" size={22} color={sharing ? colors.onSuccess : colors.brandPrimary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>Share live location</Text>
              <Text style={styles.cardSub}>
                {sharing
                  ? `Sharing ON · last sent ${lastSent ? dayjs(lastSent).format("hh:mm A") : "…"}`
                  : "Admin को पास की complaint आपको भेजने में मदद मिलती है"}
              </Text>
            </View>
            {busy ? (
              <ActivityIndicator color={colors.brandPrimary} />
            ) : (
              <Switch
                testID="location-switch"
                value={sharing}
                onValueChange={(v) => (v ? startSharing() : stopSharing())}
                trackColor={{ true: colors.success, false: colors.borderStrong }}
                thumbColor="#FFFFFF"
              />
            )}
          </View>
          {blocked && (
            <View style={styles.permBox} testID="loc-perm-blocked">
              <Text style={{ flex: 1, fontSize: 12, color: colors.onSurface }}>Location की अनुमति बंद है। Settings से allow करें।</Text>
              <Pressable onPress={openAppSettings} testID="loc-open-settings"><Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>Open Settings</Text></Pressable>
            </View>
          )}
          <Text style={styles.note}>Location सिर्फ़ app खुला होने पर share होती है।</Text>
        </View>

        <AlertSoundControl />
        <HelplineCard />

        <Pressable onPress={logout} style={styles.logout} testID="logout-btn">
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Text style={styles.logoutText}>Logout</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 24, alignItems: "center", backgroundColor: colors.brandPrimary, borderBottomLeftRadius: 24, borderBottomRightRadius: 24 },
  avatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center" },
  name: { fontSize: 20, fontWeight: "800", color: "#FFFFFF", marginTop: 12 },
  phone: { fontSize: 13, color: "#CCFBF1", marginTop: 2 },
  roleBadge: { marginTop: 10, paddingHorizontal: 12, paddingVertical: 4, backgroundColor: "rgba(255,255,255,0.2)", borderRadius: 999 },
  roleText: { fontSize: 11, color: "#FFFFFF", fontWeight: "800", letterSpacing: 0.5 },
  card: { padding: 16, backgroundColor: colors.surfaceSecondary, borderRadius: 16, borderWidth: 1, borderColor: colors.border, gap: 10 },
  icon: { width: 44, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontWeight: "700", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  note: { fontSize: 11, color: colors.muted, fontStyle: "italic" },
  permBox: { flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: 10, backgroundColor: "#FEF3C7" },
  logout: { marginTop: 24, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.error, backgroundColor: colors.surfaceSecondary },
  logoutText: { color: colors.error, fontWeight: "700" },
}));

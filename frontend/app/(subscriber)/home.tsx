import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, loadAuth, User } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";

export default function SubscriberHome() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<User | null>(null);
  const [sub, setSub] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setUser(user);
      const s = await api.mySubscription();
      setSub(s);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [fetchData]),
  );

  const usagePct = sub && sub.data_gb > 0 ? Math.min(100, (sub.used_gb / sub.data_gb) * 100) : 0;
  const daysLeft = sub ? Math.max(0, dayjs(sub.expires_at).diff(dayjs(), "day")) : 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <LinearGradient
        colors={[colors.brandPrimary, colors.brandSecondary]}
        style={[styles.header, { paddingTop: insets.top + 16 }]}
      >
        <View>
          <Text style={styles.hello}>नमस्ते 👋</Text>
          <Text style={styles.name} testID="subscriber-name">{user?.name || ""}</Text>
        </View>
        <Pressable
          onPress={() => router.push("/chat")}
          style={styles.chatFab}
          testID="chat-fab"
        >
          <Ionicons name="chatbubble-ellipses" size={22} color={colors.brandPrimary} />
        </Pressable>
      </LinearGradient>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} />}
      >
        {loading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
        ) : sub ? (
          <View style={styles.planCard} testID="active-plan-card">
            <View style={styles.planHeader}>
              <View>
                <Text style={styles.planLabel}>Active Plan</Text>
                <Text style={styles.planName}>{sub.plan_name}</Text>
              </View>
              <View style={styles.speedBadge}>
                <Ionicons name="flash" size={14} color={colors.onBrandPrimary} />
                <Text style={styles.speedText}>{sub.speed_mbps} Mbps</Text>
              </View>
            </View>

            {sub.data_gb > 0 ? (
              <>
                <View style={styles.usageRow}>
                  <Text style={styles.usageText}>{sub.used_gb.toFixed(1)} / {sub.data_gb} GB</Text>
                  <Text style={styles.usagePct}>{usagePct.toFixed(0)}%</Text>
                </View>
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${usagePct}%`, backgroundColor: colors.brandPrimary }]} />
                </View>
              </>
            ) : (
              <View style={styles.unlimited}>
                <Ionicons name="infinite" size={18} color={colors.brandPrimary} />
                <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Unlimited Data</Text>
              </View>
            )}

            <View style={styles.expiryRow}>
              <Ionicons name="calendar" size={16} color={colors.muted} />
              <Text style={styles.expiryText}>
                Expires {dayjs(sub.expires_at).format("DD MMM YYYY")} · {daysLeft} days left
              </Text>
            </View>
          </View>
        ) : (
          <View style={styles.emptyCard} testID="no-plan-card">
            <Ionicons name="wifi-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyTitle}>कोई सक्रिय प्लान नहीं</Text>
            <Text style={styles.emptySub}>अभी रिचार्ज करें और इंटरनेट का आनंद लें</Text>
            <Pressable
              onPress={() => router.push("/(subscriber)/recharge")}
              style={[styles.rechargeBtn, { backgroundColor: colors.brandPrimary }]}
              testID="recharge-now-btn"
            >
              <Text style={styles.rechargeBtnText}>अभी रिचार्ज करें</Text>
            </Pressable>
          </View>
        )}

        <Text style={styles.sectionTitle}>Quick Actions</Text>
        <View style={styles.actionsGrid}>
          <ActionTile icon="flash" label="Recharge" onPress={() => router.push("/(subscriber)/recharge")} testID="tile-recharge" />
          <ActionTile icon="alert-circle" label="Complaint" onPress={() => router.push("/(subscriber)/complaints")} testID="tile-complaint" />
          <ActionTile icon="receipt" label="Invoices" onPress={() => router.push("/(subscriber)/profile")} testID="tile-invoices" />
          <ActionTile icon="chatbubble-ellipses" label="AI Chat" onPress={() => router.push("/chat")} testID="tile-chat" />
        </View>
      </ScrollView>
    </View>
  );
}

function ActionTile({ icon, label, onPress, testID }: { icon: any; label: string; onPress: () => void; testID: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.tile, { opacity: pressed ? 0.7 : 1 }]} testID={testID}>
      <View style={[styles.tileIcon, { backgroundColor: colors.brandTertiary }]}>
        <Ionicons name={icon} size={22} color={colors.brandPrimary} />
      </View>
      <Text style={styles.tileLabel}>{label}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  header: {
    paddingHorizontal: 20,
    paddingBottom: 24,
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  hello: { color: "#CCFBF1", fontSize: 14 },
  name: { color: "#FFFFFF", fontSize: 22, fontWeight: "800", marginTop: 2 },
  chatFab: {
    width: 46, height: 46, borderRadius: 23, backgroundColor: "#FFFFFF",
    alignItems: "center", justifyContent: "center",
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 8, elevation: 4,
  },
  planCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 20,
    padding: 20,
    borderWidth: 1,
    borderColor: colors.border,
  },
  planHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 },
  planLabel: { fontSize: 12, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5 },
  planName: { fontSize: 20, fontWeight: "800", color: colors.onSurface, marginTop: 2 },
  speedBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  speedText: { color: "#FFFFFF", fontWeight: "700", fontSize: 12 },
  usageRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  usageText: { color: colors.onSurface, fontWeight: "700" },
  usagePct: { color: colors.muted },
  progressBg: { height: 10, borderRadius: 6, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  progressFill: { height: "100%", borderRadius: 6 },
  unlimited: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 4 },
  expiryRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 16 },
  expiryText: { color: colors.muted, fontSize: 12 },
  emptyCard: {
    padding: 32, alignItems: "center", backgroundColor: colors.surfaceSecondary,
    borderRadius: 20, borderWidth: 1, borderColor: colors.border,
  },
  emptyTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: 12 },
  emptySub: { fontSize: 13, color: colors.muted, marginTop: 4, textAlign: "center" },
  rechargeBtn: { marginTop: 20, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 },
  rechargeBtnText: { color: "#FFFFFF", fontWeight: "700" },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginTop: 24, marginBottom: 12 },
  actionsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  tile: {
    width: "47%", padding: 16, backgroundColor: colors.surfaceSecondary,
    borderRadius: 16, borderWidth: 1, borderColor: colors.border, gap: 12,
  },
  tileIcon: { width: 44, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  tileLabel: { color: colors.onSurface, fontWeight: "700" },
}));

import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

const inr = (n: number) => `₹${Math.round(n || 0).toLocaleString("en-IN")}`;

export default function CollectionReport() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [month, setMonth] = useState(dayjs().format("YYYY-MM"));
  const [data, setData] = useState<any | null>(null);
  const [reminders, setReminders] = useState<{ sms_enabled: boolean; items: any[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, rem] = await Promise.all([api.report(month), api.reminders()]);
      setData(r);
      setReminders(rem);
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [month]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const shift = (n: number) => setMonth(dayjs(month + "-01").add(n, "month").format("YYYY-MM"));
  const isCurrent = month === dayjs().format("YYYY-MM");

  const runNow = async () => {
    setRunning(true);
    try {
      const res = await api.runReminders();
      toast.show(`Checked ${res.checked} · sent ${res.sent} · skipped ${res.skipped}`, "success");
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setRunning(false); }
  };

  const modes = data?.by_mode || {};
  const maxDaily = Math.max(1, ...(data?.daily || []).map((d: any) => d.amount));

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Pressable onPress={() => router.back()} style={styles.back} testID="report-back">
          <Ionicons name="arrow-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Collection Report</Text>
      </View>

      <View style={styles.monthRow}>
        <Pressable onPress={() => shift(-1)} style={styles.monthBtn} testID="month-prev"><Ionicons name="chevron-back" size={20} color={colors.brandPrimary} /></Pressable>
        <Text style={styles.monthTxt} testID="month-label">{dayjs(month + "-01").format("MMMM YYYY")}</Text>
        <Pressable onPress={() => shift(1)} disabled={isCurrent} style={[styles.monthBtn, isCurrent && { opacity: 0.3 }]} testID="month-next"><Ionicons name="chevron-forward" size={20} color={colors.brandPrimary} /></Pressable>
      </View>

      {loading || !data ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }}>
          <View style={styles.hero} testID="report-total">
            <Text style={styles.heroLabel}>Total Collected</Text>
            <Text style={styles.heroValue}>{inr(data.total_collected)}</Text>
            <Text style={styles.heroSub}>{data.invoices_count} invoices</Text>
          </View>

          <View style={styles.grid}>
            <Stat label="UPI" value={inr(modes.upi?.amount)} sub={`${modes.upi?.count || 0} payments`} icon="qr-code" tint={colors.brandPrimary} testID="stat-upi" />
            <Stat label="Cash" value={inr(modes.cash?.amount)} sub={`${modes.cash?.count || 0} payments`} icon="cash" tint={colors.success} testID="stat-cash" />
            <Stat label="Pending Verification" value={inr(data.pending_verification.amount)} sub={`${data.pending_verification.count} screenshots`} icon="hourglass" tint={colors.warning} testID="stat-pending" />
            <Stat label="Dues (expired, not renewed)" value={inr(data.dues.amount)} sub={`${data.dues.count} customers`} icon="alert-circle" tint={colors.error} testID="stat-dues" />
          </View>

          {data.daily.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Daily Collection</Text>
              <View style={styles.bars}>
                {data.daily.map((d: any) => (
                  <View key={d.date} style={styles.barCol}>
                    <View style={[styles.bar, { height: Math.max(4, (d.amount / maxDaily) * 90), backgroundColor: colors.brandPrimary }]} />
                    <Text style={styles.barLbl}>{dayjs(d.date).format("D")}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          <View style={styles.card} testID="dues-card">
            <Text style={styles.cardTitle}>Dues — Follow up ({data.dues.count})</Text>
            {data.dues.items.length === 0 ? (
              <Text style={styles.empty}>कोई बकाया नहीं 🎉</Text>
            ) : data.dues.items.map((d: any) => (
              <Pressable key={d.user_id} onPress={() => Linking.openURL(`tel:${d.phone}`)} style={styles.row} testID={`due-${d.phone}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowName}>{d.name}</Text>
                  <Text style={styles.rowSub}>+91 {d.phone} · {d.plan_name} · expired {dayjs(d.expired_at).format("DD MMM")}</Text>
                </View>
                <Text style={styles.rowAmt}>{inr(d.amount)}</Text>
                <Ionicons name="call" size={18} color={colors.success} />
              </Pressable>
            ))}
          </View>

          <View style={styles.card} testID="reminders-card">
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Text style={[styles.cardTitle, { flex: 1, marginBottom: 0 }]}>Expiry SMS Reminders</Text>
              <View style={[styles.pill, { backgroundColor: reminders?.sms_enabled ? "#D1FAE5" : "#FEF3C7" }]}>
                <Text style={[styles.pillTxt, { color: reminders?.sms_enabled ? "#065F46" : "#B45309" }]}>{reminders?.sms_enabled ? "SMS ON" : "SMS OFF"}</Text>
              </View>
            </View>
            <Text style={styles.rowSub}>
              {reminders?.sms_enabled
                ? "Plan खत्म होने से 3 दिन पहले customer को अपने आप SMS जाता है (हर घंटे check)।"
                : "MSG91 Auth Key + Expiry Template ID जोड़ने पर SMS अपने आप जाएगा। अभी reminders log हो रहे हैं।"}
            </Text>
            <Pressable onPress={runNow} disabled={running} style={[styles.runBtn, { borderColor: colors.brandPrimary }]} testID="run-reminders-btn">
              {running ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (<><Ionicons name="play" size={14} color={colors.brandPrimary} /><Text style={{ color: colors.brandPrimary, fontWeight: "700", fontSize: 13 }}>Run check now</Text></>)}
            </Pressable>
            {(reminders?.items || []).slice(0, 8).map((r) => (
              <View key={r.id} style={styles.row} testID={`reminder-${r.phone}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowName}>{r.name} · +91 {r.phone}</Text>
                  <Text style={styles.rowSub}>{r.plan_name} · {r.days_left}d left · {dayjs(r.created_at).format("DD MMM hh:mm A")}</Text>
                </View>
                <View style={[styles.pill, { backgroundColor: r.status === "sent" ? "#D1FAE5" : r.status === "failed" ? "#FEE2E2" : colors.surfaceTertiary }]}>
                  <Text style={[styles.pillTxt, { color: r.status === "sent" ? "#065F46" : r.status === "failed" ? "#B91C1C" : colors.muted }]}>{r.status.toUpperCase()}</Text>
                </View>
              </View>
            ))}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

function Stat({ label, value, sub, icon, tint, testID }: any) {
  const styles = useStyles();
  return (
    <View style={styles.stat} testID={testID}>
      <View style={[styles.statIcon, { backgroundColor: tint + "20" }]}><Ionicons name={icon} size={18} color={tint} /></View>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statSub}>{sub}</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 16, paddingVertical: 10, backgroundColor: colors.surfaceSecondary },
  monthBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  monthTxt: { fontSize: 16, fontWeight: "800", color: colors.onSurface, minWidth: 160, textAlign: "center" },
  hero: { padding: 20, borderRadius: 16, backgroundColor: colors.brandPrimary },
  heroLabel: { color: "#CCFBF1", fontSize: 12, letterSpacing: 0.5, textTransform: "uppercase" },
  heroValue: { color: "#FFFFFF", fontSize: 32, fontWeight: "800", marginTop: 4 },
  heroSub: { color: "#CCFBF1", fontSize: 12, marginTop: 2 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  stat: { width: "47%", padding: 14, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  statIcon: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center", marginBottom: 10 },
  statValue: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  statLabel: { fontSize: 11, color: colors.onSurface, fontWeight: "700", marginTop: 2 },
  statSub: { fontSize: 11, color: colors.muted },
  card: { padding: 16, backgroundColor: colors.surfaceSecondary, borderRadius: 16, borderWidth: 1, borderColor: colors.border, gap: 8 },
  cardTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface, marginBottom: 4 },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 4, height: 110 },
  barCol: { flex: 1, alignItems: "center", justifyContent: "flex-end", gap: 4 },
  bar: { width: "100%", borderRadius: 3 },
  barLbl: { fontSize: 9, color: colors.muted },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border },
  rowName: { fontWeight: "700", color: colors.onSurface, fontSize: 13 },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  rowAmt: { fontWeight: "800", color: colors.error },
  empty: { color: colors.muted, fontSize: 13 },
  pill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  pillTxt: { fontSize: 10, fontWeight: "800" },
  runBtn: { marginTop: 4, height: 40, borderRadius: 10, borderWidth: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center" },
}));

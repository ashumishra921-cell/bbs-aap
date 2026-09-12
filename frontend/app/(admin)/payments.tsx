import { useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, loadAuth, User } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";
import { useLiveRefresh } from "@/src/hooks/useLiveRefresh";

const PAY_STATUS: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: "#FEF3C7", text: "#B45309", label: "Pending" },
  approved: { bg: "#D1FAE5", text: "#065F46", label: "Approved" },
  rejected: { bg: "#FEE2E2", text: "#B91C1C", label: "Rejected" },
};

export default function AdminPayments() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const [selected, setSelected] = useState<any | null>(null);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [zoom, setZoom] = useState(false);
  const [error, setError] = useState("");

  const isSuper = me?.role === "super_admin";

  const load = useCallback(async () => {
    try {
      const auth = await loadAuth();
      setMe(auth.user);
      setToken(auth.token);
      setItems(await api.payments());
      setError("");
    } catch (e: any) {
      setError(e.message || "Payments load नहीं हुए");
    } finally {
      setLoading(false);
    }
  }, []);

  useLiveRefresh(load);

  const pendingCount = items.filter((p) => p.status === "pending").length;
  const filtered = filter === "pending" ? items.filter((p) => p.status === "pending") : items;

  const imgSource = (path: string) =>
    Platform.OS === "web"
      ? { uri: api.fileUrl(path, token) }
      : { uri: api.fileUrl(path, null), headers: { Authorization: `Bearer ${token}` } };

  const approve = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.approvePayment(selected.id);
      toast.show("Payment approved · plan activated ✓", "success");
      setSelected(null);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const reject = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.rejectPayment(selected.id, reason.trim() || undefined);
      toast.show("Payment rejected", "success");
      setSelected(null); setReason("");
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>UPI Payments</Text>
        <Pressable testID="admin-all-payment-history" onPress={() => router.push("/payment-history")} style={{ minHeight: 44, justifyContent: "center" }}>
          <Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>UPI & Cash · Full payment history</Text>
        </Pressable>
        <View style={styles.segment}>
          {(["pending", "all"] as const).map((f) => (
            <Pressable key={f} testID={`pay-filter-${f}`} onPress={() => setFilter(f)} style={[styles.segItem, filter === f && { backgroundColor: colors.brandPrimary }]}>
              <Text style={[styles.segText, filter === f && { color: "#FFFFFF" }]}>
                {f === "pending" ? `PENDING${pendingCount ? ` (${pendingCount})` : ""}` : "ALL"}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {!!error && <Pressable testID="admin-payment-retry" onPress={load} style={{ padding: 16, minHeight: 44 }}><Text testID="admin-payment-error" style={{ color: colors.error }}>{error} · Retry</Text></Pressable>}

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : filtered.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="checkmark-done-circle-outline" size={60} color={colors.muted} />
          <Text style={{ color: colors.muted, marginTop: 8 }}>{filter === "pending" ? "कोई pending payment नहीं" : "कोई payment नहीं"}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10 }}>
          {filtered.map((p) => {
            const s = PAY_STATUS[p.status];
            return (
              <Pressable key={p.id} onPress={() => { setSelected(p); setReason(""); }} style={styles.card} testID={`pay-${p.id}`}>
                {token ? <Image source={imgSource(p.screenshot_path)} style={styles.thumb} resizeMode="cover" testID={`payment-proof-${p.id}`} /> : <ActivityIndicator style={styles.thumb} color={colors.brandPrimary} />}
                <View style={{ flex: 1 }}>
                  <View style={styles.cardTop}>
                    <Text style={styles.amount}>₹{p.amount}</Text>
                    <View style={[styles.badge, { backgroundColor: s.bg }]}>
                      <Text style={[styles.badgeText, { color: s.text }]}>{s.label}</Text>
                    </View>
                  </View>
                  <Text style={styles.name}>{p.user_name} · +91 {p.user_phone}</Text>
                  <Text style={styles.sub}>{p.plan_name}{p.utr ? ` · UTR ${p.utr}` : ""}</Text>
                  <Text style={styles.date}>{dayjs(p.created_at).format("DD MMM, hh:mm A")}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            );
          })}
        </ScrollView>
      )}

      <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>{selected?.user_name} · ₹{selected?.amount}</Text>
            <Text style={styles.sub}>+91 {selected?.user_phone} · {selected?.plan_name}{selected?.utr ? ` · UTR ${selected.utr}` : ""}</Text>
            {selected && token && (
              <Pressable onPress={() => setZoom(true)} testID="zoom-screenshot">
                <Image source={imgSource(selected.screenshot_path)} style={styles.bigImg} resizeMode="contain" />
                <Text style={styles.zoomHint}>Tap to enlarge</Text>
              </Pressable>
            )}
            {selected?.status === "pending" ? (
              isSuper ? (
                <>
                  <TextInput
                    testID="reject-reason-input"
                    placeholder="Reject का कारण (optional)"
                    placeholderTextColor={colors.muted}
                    value={reason}
                    onChangeText={setReason}
                    style={styles.input}
                  />
                  <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                    <Pressable onPress={reject} disabled={saving} style={[styles.btn, { backgroundColor: colors.error }]} testID="reject-payment-btn">
                      <Ionicons name="close" size={18} color="#FFFFFF" />
                      <Text style={styles.btnTxt}>Reject</Text>
                    </Pressable>
                    <Pressable onPress={approve} disabled={saving} style={[styles.btn, { backgroundColor: colors.success }]} testID="approve-payment-btn">
                      {saving ? <ActivityIndicator color="#FFFFFF" /> : (<><Ionicons name="checkmark" size={18} color="#FFFFFF" /><Text style={styles.btnTxt}>Approve & Activate</Text></>)}
                    </Pressable>
                  </View>
                </>
              ) : (
                <Text style={styles.onlySuper} testID="only-super-note">केवल Super Admin approve/reject कर सकता है</Text>
              )
            ) : (
              <Text style={styles.onlySuper}>
                {PAY_STATUS[selected?.status]?.label} by {selected?.reviewed_by} · {selected?.reviewed_at ? dayjs(selected.reviewed_at).format("DD MMM, hh:mm A") : ""}
                {selected?.reject_reason ? `\nReason: ${selected.reject_reason}` : ""}
              </Text>
            )}
            <Pressable onPress={() => setSelected(null)} style={styles.cancel}><Text style={{ color: colors.muted, fontWeight: "600" }}>Close</Text></Pressable>
          </View>
        </View>
      </Modal>

      <Modal visible={zoom} transparent animationType="fade" onRequestClose={() => setZoom(false)}>
        <Pressable style={styles.zoomBg} onPress={() => setZoom(false)} testID="zoom-close">
          {selected && token && <Image source={imgSource(selected.screenshot_path)} style={{ width: "100%", height: "85%" }} resizeMode="contain" />}
        </Pressable>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 12 },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  segment: { flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderRadius: 12, padding: 4 },
  segItem: { flex: 1, height: 36, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  segText: { fontSize: 12, fontWeight: "700", color: colors.muted },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { flexDirection: "row", gap: 12, alignItems: "center", padding: 12, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  thumb: { width: 56, height: 72, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  amount: { fontSize: 16, fontWeight: "800", color: colors.brandPrimary },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontSize: 10, fontWeight: "700" },
  name: { fontWeight: "700", color: colors.onSurface, marginTop: 4 },
  sub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  date: { fontSize: 11, color: colors.muted, marginTop: 4 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  bigImg: { width: "100%", height: 260, borderRadius: 12, marginTop: 14, backgroundColor: colors.surfaceTertiary },
  zoomHint: { textAlign: "center", fontSize: 11, color: colors.muted, marginTop: 4 },
  input: { marginTop: 12, height: 46, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, color: colors.onSurface },
  btn: { flex: 1, height: 48, borderRadius: 12, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center" },
  btnTxt: { color: "#FFFFFF", fontWeight: "700" },
  onlySuper: { marginTop: 14, color: colors.muted, fontSize: 13, textAlign: "center" },
  cancel: { marginTop: 10, height: 40, alignItems: "center", justifyContent: "center" },
  zoomBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.92)", alignItems: "center", justifyContent: "center" },
}));

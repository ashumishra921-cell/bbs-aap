import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import * as Clipboard from "expo-clipboard";
import * as ImagePicker from "expo-image-picker";
import QRCode from "react-native-qrcode-svg";
import dayjs from "dayjs";

import { api } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

const PAY_STATUS: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: "#FEF3C7", text: "#B45309", label: "Verification Pending" },
  approved: { bg: "#D1FAE5", text: "#065F46", label: "Approved" },
  rejected: { bg: "#FEE2E2", text: "#B91C1C", label: "Rejected" },
};

export default function RechargeScreen() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const { height: windowHeight } = useWindowDimensions();
  const [plans, setPlans] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [cfg, setCfg] = useState<{ upi_id: string; payee_name: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any | null>(null);
  const [utr, setUtr] = useState("");
  const [shot, setShot] = useState<{ uri: string; name: string; type: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [permBlocked, setPermBlocked] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, pay, c] = await Promise.all([api.plans(), api.payments(), api.paymentConfig()]);
      setPlans(p);
      setPayments(pay);
      setCfg(c);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  useEffect(() => { if (!selected) { setUtr(""); setShot(null); } }, [selected]);

  const pending = payments.find((p) => p.status === "pending");
  const upiLink = selected && cfg
    ? `upi://pay?pa=${encodeURIComponent(cfg.upi_id)}&pn=${encodeURIComponent(cfg.payee_name)}&am=${selected.price}&cu=INR&tn=${encodeURIComponent(`${selected.name} recharge`)}`
    : "";

  const copyUpi = async () => {
    if (!cfg) return;
    await Clipboard.setStringAsync(cfg.upi_id);
    toast.show("UPI ID copied ✓", "success");
  };

  const openUpiApp = async () => {
    if (Platform.OS === "web") { toast.show("UPI app केवल mobile पर खुलेगा — UPI ID copy करके pay करें", "info"); return; }
    try {
      const ok = await Linking.canOpenURL(upiLink);
      if (!ok) throw new Error();
      await Linking.openURL(upiLink);
    } catch {
      toast.show("कोई UPI app नहीं मिला — UPI ID copy करके pay करें", "error");
    }
  };

  const pickScreenshot = async () => {
    let perm = await ImagePicker.getMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      if (!perm.canAskAgain) { setPermBlocked(true); return; }
      perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) { if (!perm.canAskAgain) setPermBlocked(true); else toast.show("Screenshot चुनने के लिए Photos की अनुमति दें", "error"); return; }
    }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7, allowsEditing: false });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setShot({ uri: a.uri, name: a.fileName || `screenshot-${Date.now()}.jpg`, type: a.mimeType || "image/jpeg" });
  };

  const submit = async () => {
    if (!selected || !shot) { toast.show("Payment का screenshot upload करें", "error"); return; }
    setUploading(true);
    try {
      const { path } = await api.uploadScreenshot(shot.uri, shot.name, shot.type);
      setUploading(false);
      setSubmitting(true);
      await api.createPayment({ plan_id: selected.id, screenshot_path: path, utr: utr.trim() || undefined });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.show("Payment submit हो गया — verification के बाद plan activate होगा", "success");
      setSelected(null);
      load();
    } catch (e: any) {
      toast.show(e.message || "Submit failed", "error");
    } finally {
      setUploading(false);
      setSubmitting(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.headerTitle}>Recharge Plans</Text>
        <Text style={styles.headerSub}>UPI से pay करें, screenshot upload करें</Text>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32, gap: 12 }}>
          {payments.length > 0 && (
            <View style={styles.historyCard} testID="payment-history">
              <Text style={styles.historyTitle}>My Payments</Text>
              {payments.slice(0, 3).map((p) => {
                const s = PAY_STATUS[p.status];
                return (
                  <Pressable
                    key={p.id}
                    onPress={() => p.invoice_id && router.push(`/invoice/${p.invoice_id}`)}
                    style={styles.historyRow}
                    testID={`payment-${p.status}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.historyPlan}>{p.plan_name} · ₹{p.amount}</Text>
                      <Text style={styles.historyDate}>
                        {dayjs(p.created_at).format("DD MMM, hh:mm A")}{p.reject_reason ? ` · ${p.reject_reason}` : ""}
                      </Text>
                    </View>
                    <View style={[styles.badge, { backgroundColor: s.bg }]}>
                      <Text style={[styles.badgeText, { color: s.text }]}>{s.label}</Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
          )}

          {plans.map((p) => (
            <View key={p.id} style={styles.planCard} testID={`plan-${p.name}`}>
              <View style={styles.planTop}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.planName}>{p.name}</Text>
                  <Text style={styles.planDesc}>{p.description}</Text>
                </View>
                <Text style={styles.price}>₹{p.price}</Text>
              </View>
              <View style={styles.metaRow}>
                <Meta icon="flash" text={`${p.speed_mbps} Mbps`} />
                <Meta icon="cloud-download" text={p.data_gb ? `${p.data_gb} GB` : "Unlimited"} />
                <Meta icon="calendar" text={`${p.validity_days} days`} />
              </View>
              <Pressable
                onPress={() => pending ? toast.show("आपका एक payment verification में है, कृपया प्रतीक्षा करें", "info") : setSelected(p)}
                style={({ pressed }) => [styles.payBtn, { backgroundColor: pending ? colors.borderStrong : colors.brandPrimary, opacity: pressed ? 0.85 : 1 }]}
                testID={`recharge-btn-${p.name}`}
              >
                <Ionicons name="qr-code" size={16} color="#FFFFFF" />
                <Text style={styles.payText}>Pay via UPI</Text>
              </Pressable>
            </View>
          ))}
        </ScrollView>
      )}

      <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
        <KeyboardAvoidingView style={styles.modalBg} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 16, height: windowHeight * 0.92, maxHeight: windowHeight - insets.top }]} testID="upi-payment-sheet">
            <View style={styles.grabber} />
            <View style={styles.sheetHeader}>
              <Text style={styles.modalTitle}>UPI Payment</Text>
              <Pressable testID="close-upi-payment" accessibilityLabel="Close UPI payment" disabled={uploading || submitting} onPress={() => setSelected(null)} style={styles.closeSheet}>
                <Ionicons name="close" size={24} color={colors.onSurface} />
              </Pressable>
            </View>
            <Text style={styles.modalSub}>{selected?.name} · ₹{selected?.price}</Text>
            <ScrollView style={styles.sheetScroll} contentContainerStyle={{ paddingBottom: 16 }} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" testID="upi-payment-scroll">
              <View style={styles.qrBox}>
                {upiLink ? <QRCode value={upiLink} size={150} /> : null}
                <Text style={styles.qrHint}>किसी भी UPI app से scan करें</Text>
              </View>

              <Text style={styles.label}>Step 1 · UPI ID पर ₹{selected?.price} भेजें</Text>
              <Pressable onPress={copyUpi} style={styles.upiRow} testID="copy-upi-btn">
                <View style={{ flex: 1 }}>
                  <Text style={styles.upiId}>{cfg?.upi_id}</Text>
                  <Text style={styles.upiName}>{cfg?.payee_name}</Text>
                </View>
                <Ionicons name="copy-outline" size={20} color={colors.brandPrimary} />
              </Pressable>
              <Pressable onPress={openUpiApp} style={[styles.outlineBtn, { borderColor: colors.brandPrimary }]} testID="open-upi-app-btn">
                <Ionicons name="phone-portrait-outline" size={18} color={colors.brandPrimary} />
                <Text style={[styles.outlineTxt, { color: colors.brandPrimary }]}>Pay via UPI app (GPay / PhonePe / Paytm)</Text>
              </Pressable>

              <Text style={styles.label}>Step 2 · Payment screenshot upload करें *</Text>
              {shot ? (
                <View style={styles.previewWrap}>
                  <Image source={{ uri: shot.uri }} style={styles.preview} resizeMode="cover" />
                  <Pressable onPress={pickScreenshot} style={styles.changeBtn} testID="change-screenshot-btn">
                    <Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>Change</Text>
                  </Pressable>
                </View>
              ) : (
                <Pressable onPress={pickScreenshot} style={styles.uploadBox} testID="pick-screenshot-btn">
                  <Ionicons name="image-outline" size={32} color={colors.brandPrimary} />
                  <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: 6 }}>Screenshot चुनें</Text>
                  <Text style={{ color: colors.muted, fontSize: 12 }}>Gallery से payment success screenshot</Text>
                </Pressable>
              )}
              {permBlocked && (
                <View style={styles.permBox} testID="perm-blocked">
                  <Text style={{ color: colors.onSurface, fontSize: 12, flex: 1 }}>Photos की अनुमति बंद है। Settings से allow करें।</Text>
                  <Pressable onPress={() => Linking.openSettings()} testID="open-settings-btn">
                    <Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>Open Settings</Text>
                  </Pressable>
                </View>
              )}

              <Text style={styles.label}>UTR / Transaction ID (optional)</Text>
              <TextInput
                testID="utr-input"
                placeholder="12 अंकों का UTR नंबर"
                placeholderTextColor={colors.muted}
                value={utr}
                onChangeText={setUtr}
                autoCapitalize="characters"
                style={styles.input}
              />
            </ScrollView>

            <View style={styles.sheetFooter}>
            <Pressable
              onPress={submit}
              disabled={uploading || submitting || !shot}
              style={({ pressed }) => [styles.confirmBtn, { backgroundColor: shot ? colors.brandPrimary : colors.borderStrong, opacity: pressed || uploading || submitting ? 0.85 : 1 }]}
              testID="submit-payment-btn"
            >
              {uploading || submitting ? (
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                  <ActivityIndicator color="#FFFFFF" />
                  <Text style={styles.confirmText}>{uploading ? "Uploading…" : "Submitting…"}</Text>
                </View>
              ) : (
                <Text style={styles.confirmText}>Submit for Verification</Text>
              )}
            </Pressable>
            <Pressable disabled={uploading || submitting} onPress={() => setSelected(null)} style={styles.cancelBtn} testID="cancel-pay">
              <Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text>
            </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

function Meta({ icon, text }: { icon: any; text: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.meta}>
      <Ionicons name={icon} size={14} color={colors.brandPrimary} />
      <Text style={styles.metaText}>{text}</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 16, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  headerSub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  historyCard: { backgroundColor: colors.surfaceSecondary, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: colors.border, gap: 10 },
  historyTitle: { fontSize: 13, fontWeight: "800", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5 },
  historyRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  historyPlan: { fontWeight: "700", color: colors.onSurface },
  historyDate: { fontSize: 11, color: colors.muted, marginTop: 2 },
  badge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  badgeText: { fontSize: 10, fontWeight: "700" },
  planCard: { backgroundColor: colors.surfaceSecondary, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 12 },
  planTop: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  planName: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  planDesc: { fontSize: 12, color: colors.muted, marginTop: 2 },
  price: { fontSize: 22, fontWeight: "800", color: colors.brandPrimary },
  metaRow: { flexDirection: "row", gap: 12, flexWrap: "wrap" },
  meta: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  metaText: { color: colors.onBrandTertiary, fontSize: 12, fontWeight: "600" },
  payBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 44, borderRadius: 12 },
  payText: { color: "#FFFFFF", fontWeight: "700" },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  sheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexShrink: 0 },
  closeSheet: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  sheetScroll: { flex: 1, minHeight: 0 },
  sheetFooter: { flexShrink: 0 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  modalSub: { fontSize: 14, color: colors.muted, marginTop: 4 },
  qrBox: { alignItems: "center", padding: 20, backgroundColor: "#FFFFFF", borderRadius: 16, marginTop: 16, borderWidth: 1, borderColor: colors.border },
  qrHint: { color: colors.muted, marginTop: 10, fontSize: 12 },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 16, marginBottom: 6 },
  upiRow: { flexDirection: "row", alignItems: "center", gap: 10, padding: 14, borderRadius: 12, backgroundColor: colors.brandTertiary },
  upiId: { fontSize: 16, fontWeight: "800", color: colors.onBrandTertiary },
  upiName: { fontSize: 12, color: colors.onBrandTertiary, marginTop: 2 },
  outlineBtn: { marginTop: 10, height: 46, borderRadius: 12, borderWidth: 1, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center" },
  outlineTxt: { fontWeight: "700", fontSize: 13 },
  uploadBox: { alignItems: "center", padding: 20, borderRadius: 14, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.brandPrimary, backgroundColor: colors.surfaceTertiary },
  previewWrap: { flexDirection: "row", alignItems: "center", gap: 12 },
  preview: { width: 90, height: 120, borderRadius: 10, backgroundColor: colors.surfaceTertiary },
  changeBtn: { height: 44, paddingHorizontal: 16, justifyContent: "center" },
  permBox: { marginTop: 8, flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: 10, backgroundColor: "#FEF3C7" },
  input: { height: 48, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, fontSize: 15, color: colors.onSurface },
  confirmBtn: { marginTop: 14, height: 52, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  confirmText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  cancelBtn: { marginTop: 6, height: 44, alignItems: "center", justifyContent: "center" },
}));

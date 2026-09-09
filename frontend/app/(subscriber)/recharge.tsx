import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";

import { api } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function RechargeScreen() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any | null>(null);
  const [upi, setUpi] = useState("");
  const [payLoading, setPayLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = await api.plans();
      setPlans(p);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openPay = (p: any) => {
    setSelected(p);
    setUpi("");
    setModalOpen(true);
  };

  const doPay = async () => {
    if (!upi.includes("@")) {
      toast.show("मान्य UPI ID दर्ज करें (e.g. name@upi)", "error");
      return;
    }
    if (!selected) return;
    setPayLoading(true);
    try {
      const res = await api.recharge(selected.id, upi);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.show("रिचार्ज सफल! ✓", "success");
      setModalOpen(false);
      router.push(`/invoice/${res.invoice.id}`);
    } catch (e: any) {
      toast.show(e.message || "Payment failed", "error");
    } finally {
      setPayLoading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.headerTitle}>Recharge Plans</Text>
        <Text style={styles.headerSub}>अपने लिए सही प्लान चुनें</Text>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32, gap: 12 }}>
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
                onPress={() => openPay(p)}
                style={({ pressed }) => [styles.payBtn, { backgroundColor: colors.brandPrimary, opacity: pressed ? 0.85 : 1 }]}
                testID={`recharge-btn-${p.name}`}
              >
                <Ionicons name="qr-code" size={16} color="#FFFFFF" />
                <Text style={styles.payText}>Pay via UPI</Text>
              </Pressable>
            </View>
          ))}
        </ScrollView>
      )}

      <Modal visible={modalOpen} transparent animationType="slide" onRequestClose={() => setModalOpen(false)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>UPI Payment (Mock)</Text>
            <Text style={styles.modalSub}>{selected?.name} · ₹{selected?.price}</Text>

            <View style={styles.qrBox}>
              <Ionicons name="qr-code" size={100} color={colors.onSurface} />
              <Text style={styles.qrHint}>Scan or enter UPI ID</Text>
            </View>

            <TextInput
              testID="upi-input"
              placeholder="yourname@upi"
              placeholderTextColor={colors.muted}
              value={upi}
              onChangeText={setUpi}
              autoCapitalize="none"
              style={styles.upiInput}
            />
            <Pressable
              onPress={doPay}
              disabled={payLoading}
              style={({ pressed }) => [styles.confirmBtn, { backgroundColor: colors.brandPrimary, opacity: pressed || payLoading ? 0.85 : 1 }]}
              testID="confirm-pay-btn"
            >
              {payLoading ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.confirmText}>Confirm & Pay</Text>}
            </Pressable>
            <Pressable onPress={() => setModalOpen(false)} style={styles.cancelBtn} testID="cancel-pay">
              <Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text>
            </Pressable>
          </View>
        </View>
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
  planCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: 16, padding: 16,
    borderWidth: 1, borderColor: colors.border, gap: 12,
  },
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
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  modalSub: { fontSize: 14, color: colors.muted, marginTop: 4 },
  qrBox: { alignItems: "center", padding: 24, backgroundColor: colors.surfaceTertiary, borderRadius: 16, marginTop: 16 },
  qrHint: { color: colors.muted, marginTop: 8, fontSize: 12 },
  upiInput: {
    marginTop: 16, height: 52, borderRadius: 12, backgroundColor: colors.surfaceTertiary,
    borderWidth: 1, borderColor: colors.border, paddingHorizontal: 16, fontSize: 16, color: colors.onSurface,
  },
  confirmBtn: { marginTop: 16, height: 52, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  confirmText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  cancelBtn: { marginTop: 8, height: 44, alignItems: "center", justifyContent: "center" },
}));

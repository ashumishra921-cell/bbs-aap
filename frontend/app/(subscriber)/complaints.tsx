import { useFocusEffect } from "expo-router";
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
import dayjs from "dayjs";

import { api } from "@/src/api";
import { getCurrentLocation, openAppSettings } from "@/src/utils/location";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

const STATUS_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  open: { bg: "#FEF3C7", text: "#B45309", label: "Open" },
  assigned: { bg: "#DBEAFE", text: "#1D4ED8", label: "Assigned" },
  in_progress: { bg: "#E0E7FF", text: "#4338CA", label: "In Progress" },
  resolved: { bg: "#D1FAE5", text: "#065F46", label: "Resolved" },
};

export default function ComplaintsScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [priority, setPriority] = useState<"low" | "medium" | "high">("medium");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const c = await api.complaints();
      setItems(c);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const submit = async () => {
    if (!title.trim() || !desc.trim()) {
      toast.show("Title और details दोनों भरें", "error");
      return;
    }
    setSubmitting(true);
    try {
      await api.createComplaint({ title, description: desc, priority, lat: loc?.lat, lng: loc?.lng });
      toast.show("शिकायत दर्ज हो गई ✓", "success");
      setTitle(""); setDesc(""); setPriority("medium"); setLoc(null);
      setModalOpen(false);
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(null);
  const [locBusy, setLocBusy] = useState(false);
  const [locBlocked, setLocBlocked] = useState(false);

  const attachLocation = async () => {
    if (loc) { setLoc(null); return; }
    setLocBusy(true);
    const res = await getCurrentLocation();
    setLocBusy(false);
    if (res.ok) { setLoc({ lat: res.lat, lng: res.lng }); setLocBlocked(false); return; }
    if (res.reason === "blocked") setLocBlocked(true);
    else toast.show(res.reason === "denied" ? "Location की अनुमति नहीं मिली" : "Location उपलब्ध नहीं", "error");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.headerTitle}>My Complaints</Text>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : items.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="checkmark-circle" size={64} color={colors.success} />
          <Text style={styles.emptyTitle}>कोई शिकायत नहीं</Text>
          <Text style={styles.emptySub}>सब कुछ ठीक चल रहा है!</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 100 }}>
          {items.map((c) => {
            const s = STATUS_COLORS[c.status] || STATUS_COLORS.open;
            return (
              <View key={c.id} style={styles.card} testID={`complaint-${c.ticket_no}`}>
                <View style={styles.cardTop}>
                  <Text style={styles.ticket}>{c.ticket_no}</Text>
                  <View style={[styles.badge, { backgroundColor: s.bg }]}>
                    <Text style={[styles.badgeText, { color: s.text }]}>{s.label}</Text>
                  </View>
                </View>
                <Text style={styles.cardTitle}>{c.title}</Text>
                <Text style={styles.cardDesc} numberOfLines={2}>{c.description}</Text>
                {c.assigned_to_name && (
                  <Text style={styles.assign}>Assigned to: {c.assigned_to_name}</Text>
                )}
                {c.resolution_note && (
                  <View style={styles.resolveBox}>
                    <Text style={styles.resolveLabel}>Resolution</Text>
                    <Text style={styles.resolveText}>{c.resolution_note}</Text>
                  </View>
                )}
                <Text style={styles.date}>{dayjs(c.created_at).format("DD MMM, hh:mm A")}</Text>
              </View>
            );
          })}
        </ScrollView>
      )}

      <Pressable
        onPress={() => setModalOpen(true)}
        style={[styles.fab, { backgroundColor: colors.brandPrimary, bottom: insets.bottom + 24 }]}
        testID="new-complaint-fab"
      >
        <Ionicons name="add" size={28} color="#FFFFFF" />
      </Pressable>

      <Modal visible={modalOpen} transparent animationType="slide">
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>नई शिकायत दर्ज करें</Text>

            <Text style={styles.label}>Title</Text>
            <TextInput
              testID="complaint-title-input"
              placeholder="Slow internet, No connection..."
              placeholderTextColor={colors.muted}
              value={title}
              onChangeText={setTitle}
              style={styles.input}
            />

            <Text style={styles.label}>Description</Text>
            <TextInput
              testID="complaint-desc-input"
              placeholder="विस्तार से बताएं..."
              placeholderTextColor={colors.muted}
              value={desc}
              onChangeText={setDesc}
              multiline
              numberOfLines={4}
              style={[styles.input, { height: 100, textAlignVertical: "top", paddingTop: 12 }]}
            />

            <Text style={styles.label}>Priority</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              {(["low", "medium", "high"] as const).map((p) => (
                <Pressable
                  key={p}
                  testID={`priority-${p}`}
                  onPress={() => setPriority(p)}
                  style={[
                    styles.chip,
                    priority === p && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
                  ]}
                >
                  <Text style={[styles.chipText, priority === p && { color: "#FFFFFF" }]}>{p.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>

            <Pressable onPress={attachLocation} style={[styles.locRow, loc && { borderColor: colors.success }]} testID="attach-location-btn">
              {locBusy ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
                <Ionicons name={loc ? "checkmark-circle" : "location-outline"} size={20} color={loc ? colors.success : colors.brandPrimary} />
              )}
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: "700", color: colors.onSurface, fontSize: 13 }}>
                  {loc ? "Location जोड़ी गई ✓ (tap to remove)" : "मेरी location जोड़ें"}
                </Text>
                <Text style={{ fontSize: 11, color: colors.muted }}>नज़दीकी technician जल्दी भेजने में मदद मिलती है</Text>
              </View>
            </Pressable>
            {locBlocked && (
              <View style={styles.permBox} testID="loc-perm-blocked">
                <Text style={{ flex: 1, fontSize: 12, color: colors.onSurface }}>Location की अनुमति बंद है। Settings से allow करें।</Text>
                <Pressable onPress={openAppSettings} testID="loc-open-settings"><Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>Open Settings</Text></Pressable>
              </View>
            )}

            <Pressable
              onPress={submit}
              disabled={submitting}
              style={[styles.submitBtn, { backgroundColor: colors.brandPrimary, opacity: submitting ? 0.85 : 1 }]}
              testID="submit-complaint-btn"
            >
              {submitting ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.submitText}>Submit</Text>}
            </Pressable>
            <Pressable onPress={() => setModalOpen(false)} style={styles.cancel}>
              <Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  locRow: { marginTop: 14, flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  permBox: { marginTop: 8, flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: 10, backgroundColor: "#FEF3C7" },
  header: { paddingHorizontal: 20, paddingBottom: 16, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 40, gap: 8 },
  emptyTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: 12 },
  emptySub: { color: colors.muted },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 6 },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  ticket: { fontSize: 11, fontWeight: "700", color: colors.muted, letterSpacing: 0.5 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  cardTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 4 },
  cardDesc: { fontSize: 13, color: colors.onSurfaceSecondary },
  assign: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  resolveBox: { backgroundColor: colors.brandTertiary, padding: 10, borderRadius: 10, marginTop: 4 },
  resolveLabel: { fontSize: 10, color: colors.onBrandTertiary, fontWeight: "700", textTransform: "uppercase" },
  resolveText: { fontSize: 13, color: colors.onBrandTertiary, marginTop: 2 },
  date: { fontSize: 11, color: colors.muted, marginTop: 4 },
  fab: {
    position: "absolute", right: 20, width: 56, height: 56, borderRadius: 28,
    alignItems: "center", justifyContent: "center",
    shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 10, elevation: 6,
  },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginBottom: 8 },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 12, marginBottom: 6 },
  input: { height: 48, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, color: colors.onSurface, fontSize: 15 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  chipText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  submitBtn: { marginTop: 20, height: 50, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  submitText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  cancel: { marginTop: 8, height: 40, alignItems: "center", justifyContent: "center" },
}));

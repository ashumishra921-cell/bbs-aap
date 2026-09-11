import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, loadAuth } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

const STATUS_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  open: { bg: "#FEF3C7", text: "#B45309", label: "New" },
  assigned: { bg: "#DBEAFE", text: "#1D4ED8", label: "Assigned" },
  in_progress: { bg: "#E0E7FF", text: "#4338CA", label: "In Progress" },
  resolved: { bg: "#D1FAE5", text: "#065F46", label: "Resolved" },
};

export default function TeamAssigned() {
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [meId, setMeId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"new" | "active" | "resolved">("active");
  const [selected, setSelected] = useState<any | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setMeId(user?.id || "");
      const c = await api.complaints();
      setItems(c);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const newCount = items.filter((c) => !c.assigned_to).length;
  const filtered = items.filter((c) =>
    filter === "new" ? !c.assigned_to : filter === "active" ? !!c.assigned_to && c.status !== "resolved" : c.status === "resolved",
  );

  const accept = async (c: any) => {
    setSaving(true);
    try {
      await api.updateComplaint(c.id, { assigned_to: meId });
      toast.show("टिकट स्वीकार किया ✓", "success");
      setSelected(null);
      setFilter("active");
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (status: string) => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.updateComplaint(selected.id, { status, resolution_note: status === "resolved" && note ? note : undefined });
      toast.show("Updated ✓", "success");
      setSelected(null); setNote("");
      load();
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.headerTitle}>Tickets</Text>
        <View style={styles.segment}>
          {(["new", "active", "resolved"] as const).map((f) => (
            <Pressable
              key={f}
              testID={`filter-${f}`}
              onPress={() => setFilter(f)}
              style={[styles.segItem, filter === f && { backgroundColor: colors.brandPrimary }]}
            >
              <Text style={[styles.segText, filter === f && { color: "#FFFFFF" }]}>
                {f === "new" ? `NEW${newCount ? ` (${newCount})` : ""}` : f.toUpperCase()}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : filtered.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="briefcase-outline" size={60} color={colors.muted} />
          <Text style={{ color: colors.muted, marginTop: 8 }}>
            {filter === "new" ? "कोई नया टिकट नहीं" : filter === "active" ? "कोई सक्रिय टिकट नहीं" : "कोई हल किया टिकट नहीं"}
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
          {filtered.map((c) => {
            const s = STATUS_COLORS[c.status];
            return (
              <Pressable
                key={c.id}
                onPress={() => { setSelected(c); setNote(c.resolution_note || ""); }}
                style={styles.card}
                testID={`ticket-${c.ticket_no}`}
              >
                <View style={styles.cardTop}>
                  <Text style={styles.ticket}>{c.ticket_no}</Text>
                  <View style={[styles.badge, { backgroundColor: s.bg }]}>
                    <Text style={[styles.badgeText, { color: s.text }]}>{s.label}</Text>
                  </View>
                </View>
                <Text style={styles.cardTitle}>{c.title}</Text>
                <Text style={styles.cardDesc} numberOfLines={2}>{c.description}</Text>
                <View style={styles.userRow}>
                  <Ionicons name="person" size={12} color={colors.muted} />
                  <Text style={styles.userTxt}>{c.user_name} · {c.user_phone}</Text>
                </View>
                {c.auto_assigned && (
                  <View style={styles.userRow}>
                    <Ionicons name="flash" size={12} color={colors.brandPrimary} />
                    <Text style={[styles.userTxt, { color: colors.brandPrimary }]}>Auto-assigned to you</Text>
                  </View>
                )}
                <Text style={styles.date}>{dayjs(c.created_at).format("DD MMM, hh:mm A")}</Text>
                {!c.assigned_to && (
                  <Pressable
                    onPress={() => accept(c)}
                    disabled={saving}
                    style={[styles.acceptBtn, { backgroundColor: colors.brandPrimary }]}
                    testID={`accept-${c.ticket_no}`}
                  >
                    <Ionicons name="hand-right" size={16} color="#FFFFFF" />
                    <Text style={styles.actionText}>Accept Ticket</Text>
                  </Pressable>
                )}
              </Pressable>
            );
          })}
        </ScrollView>
      )}

      <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>{selected?.title}</Text>
            <Text style={styles.modalSub}>{selected?.ticket_no}</Text>
            <Text style={styles.desc}>{selected?.description}</Text>

            <Text style={styles.label}>Resolution Note</Text>
            <TextInput
              testID="resolution-input"
              placeholder="निदान लिखें..."
              placeholderTextColor={colors.muted}
              value={note}
              onChangeText={setNote}
              multiline
              style={styles.input}
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              {!selected?.assigned_to && (
                <Pressable
                  onPress={() => accept(selected)}
                  disabled={saving}
                  style={[styles.actionBtn, { backgroundColor: colors.brandPrimary }]}
                  testID="accept-ticket"
                >
                  <Text style={styles.actionText}>Accept</Text>
                </Pressable>
              )}
              <Pressable
                onPress={() => updateStatus("in_progress")}
                disabled={saving}
                style={[styles.actionBtn, { backgroundColor: colors.info }]}
                testID="mark-in-progress"
              >
                <Text style={styles.actionText}>In Progress</Text>
              </Pressable>
              <Pressable
                onPress={() => updateStatus("resolved")}
                disabled={saving}
                style={[styles.actionBtn, { backgroundColor: colors.success }]}
                testID="mark-resolved"
              >
                <Text style={styles.actionText}>Resolve</Text>
              </Pressable>
            </View>
            <Pressable onPress={() => setSelected(null)} style={styles.cancel}>
              <Text style={{ color: colors.muted, fontWeight: "600" }}>Close</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 12 },
  headerTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  segment: { flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderRadius: 10, padding: 4 },
  segItem: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 8 },
  segText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, gap: 6 },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  ticket: { fontSize: 11, fontWeight: "700", color: colors.muted },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  cardTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  cardDesc: { fontSize: 13, color: colors.onSurfaceSecondary },
  userRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  userTxt: { fontSize: 12, color: colors.muted },
  date: { fontSize: 11, color: colors.muted },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  modalSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  desc: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 12 },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 16, marginBottom: 6 },
  input: { minHeight: 80, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, padding: 12, textAlignVertical: "top", color: colors.onSurface },
  actionBtn: { flex: 1, height: 46, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  acceptBtn: { marginTop: 8, height: 42, borderRadius: 10, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center" },
  actionText: { color: "#FFFFFF", fontWeight: "700" },
  cancel: { marginTop: 8, height: 40, alignItems: "center", justifyContent: "center" },
}));

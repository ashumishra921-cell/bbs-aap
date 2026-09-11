import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

const STATUS_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  open: { bg: "#FEF3C7", text: "#B45309", label: "Open" },
  assigned: { bg: "#DBEAFE", text: "#1D4ED8", label: "Assigned" },
  in_progress: { bg: "#E0E7FF", text: "#4338CA", label: "In Progress" },
  resolved: { bg: "#D1FAE5", text: "#065F46", label: "Resolved" },
};

export default function AdminComplaints() {
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [team, setTeam] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any | null>(null);
  const [filter, setFilter] = useState<"all" | "open" | "resolved">("all");
  const [autoAssign, setAutoAssign] = useState<boolean>(true);

  const load = useCallback(async () => {
    try {
      const [c, t, s] = await Promise.all([api.complaints(), api.team(), api.settings()]);
      setItems(c);
      setTeam(t.filter((x: any) => x.role === "team"));
      setAutoAssign(s.auto_assign);
    } finally { setLoading(false); }
  }, []);

  const toggleAutoAssign = async (v: boolean) => {
    setAutoAssign(v);
    try {
      await api.updateSettings({ auto_assign: v });
      toast.show(v ? "Auto-assign ON" : "Auto-assign OFF", "success");
    } catch (e: any) { setAutoAssign(!v); toast.show(e.message, "error"); }
  };

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const filtered = items.filter((c) =>
    filter === "all" ? true : filter === "open" ? c.status !== "resolved" : c.status === "resolved"
  );

  const assign = async (memberId: string) => {
    if (!selected) return;
    try {
      await api.updateComplaint(selected.id, { assigned_to: memberId });
      toast.show("Assigned ✓", "success");
      setSelected(null);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>All Complaints</Text>
        <View style={styles.autoRow} testID="auto-assign-row">
          <Ionicons name="flash" size={16} color={colors.brandPrimary} />
          <View style={{ flex: 1 }}>
            <Text style={styles.autoTitle}>Auto-assign to technician</Text>
            <Text style={styles.autoSub}>नई शिकायत सबसे कम व्यस्त टेक्नीशियन को अपने आप जाएगी</Text>
          </View>
          <Switch
            testID="auto-assign-switch"
            value={autoAssign}
            onValueChange={toggleAutoAssign}
            trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
            thumbColor="#FFFFFF"
          />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingRight: 16 }}>
          {(["all", "open", "resolved"] as const).map((f) => (
            <Pressable
              key={f}
              testID={`filter-${f}`}
              onPress={() => setFilter(f)}
              style={[styles.chip, filter === f && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]}
            >
              <Text style={[styles.chipTxt, filter === f && { color: "#FFFFFF" }]}>{f.toUpperCase()}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10 }}>
          {filtered.map((c) => {
            const s = STATUS_COLORS[c.status];
            return (
              <Pressable key={c.id} onPress={() => setSelected(c)} style={styles.card} testID={`ac-${c.ticket_no}`}>
                <View style={styles.cardTop}>
                  <Text style={styles.ticket}>{c.ticket_no}</Text>
                  <View style={[styles.badge, { backgroundColor: s.bg }]}>
                    <Text style={[styles.badgeText, { color: s.text }]}>{s.label}</Text>
                  </View>
                </View>
                <Text style={styles.cardTitle}>{c.title}</Text>
                <Text style={styles.cardSub}>{c.user_name} · {c.user_phone}</Text>
                {c.assigned_to_name && <Text style={styles.assign}>→ {c.assigned_to_name}</Text>}
                <Text style={styles.date}>{dayjs(c.created_at).format("DD MMM, hh:mm A")}</Text>
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
            <Text style={styles.modalSub}>{selected?.ticket_no} · {selected?.user_name}</Text>
            <Text style={styles.desc}>{selected?.description}</Text>

            <Text style={styles.label}>Assign to Team Member</Text>
            {team.length === 0 ? (
              <Text style={{ color: colors.muted }}>No team members. Add one first.</Text>
            ) : (
              <View style={{ gap: 8 }}>
                {team.map((m) => (
                  <Pressable
                    key={m.id}
                    onPress={() => assign(m.id)}
                    style={styles.memberRow}
                    testID={`assign-${m.phone}`}
                  >
                    <Ionicons name="person-circle" size={28} color={colors.brandPrimary} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: "700", color: colors.onSurface }}>{m.name}</Text>
                      <Text style={{ fontSize: 12, color: colors.muted }}>+91 {m.phone}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={20} color={colors.muted} />
                  </Pressable>
                ))}
              </View>
            )}
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
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  autoRow: { flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: 12, backgroundColor: colors.brandTertiary },
  autoTitle: { fontSize: 13, fontWeight: "700", color: colors.onBrandTertiary },
  autoSub: { fontSize: 11, color: colors.onBrandTertiary, marginTop: 1 },
  chip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary, flexShrink: 0 },
  chipTxt: { fontSize: 11, fontWeight: "700", color: colors.onSurface },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, gap: 4 },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  ticket: { fontSize: 11, fontWeight: "700", color: colors.muted },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  cardTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  cardSub: { fontSize: 12, color: colors.muted },
  assign: { fontSize: 12, color: colors.brandPrimary, fontWeight: "700", marginTop: 2 },
  date: { fontSize: 11, color: colors.muted, marginTop: 4 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  modalSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  desc: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 12 },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 16, marginBottom: 8 },
  memberRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, backgroundColor: colors.surfaceTertiary, borderRadius: 12 },
  cancel: { marginTop: 12, height: 40, alignItems: "center", justifyContent: "center" },
}));

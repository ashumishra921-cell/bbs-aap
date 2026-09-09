import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";

import { api, loadAuth } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

type Msg = { id: string; role: "user" | "assistant"; text: string };

export default function ChatScreen() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const listRef = useRef<FlatList<Msg>>(null);

  useEffect(() => {
    (async () => {
      try {
        const { token } = await loadAuth();
        if (!token) { router.replace("/"); return; }
        const h = await api.chatHistory();
        if (h.length === 0) {
          setMsgs([
            {
              id: "welcome",
              role: "assistant",
              text: "नमस्ते! 👋 मैं Broadband Solutions 24×7 का AI सहायक हूँ। मैं आपकी क्या मदद कर सकता हूँ? (जैसे: प्लान, रिचार्ज, धीमा इंटरनेट, बिल)",
            },
          ]);
        } else {
          setMsgs(h.map((m: any) => ({ id: m.id, role: m.role, text: m.text })));
        }
      } finally { setLoading(false); }
    })();
  }, []);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", text };
    setMsgs((m) => [...m, userMsg]);
    setInput("");
    setSending(true);
    try {
      const res = await api.chat(text);
      setMsgs((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", text: res.reply }]);
    } catch (e: any) {
      toast.show(e.message || "Chat failed", "error");
    } finally {
      setSending(false);
    }
  };

  const clear = async () => {
    try {
      await api.clearChat();
      setMsgs([{ id: "welcome", role: "assistant", text: "चैट साफ़ हो गई। कैसे मदद करूँ?" }]);
      toast.show("Cleared", "success");
    } catch {}
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={0}
    >
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="chat-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>AI Support</Text>
          <Text style={styles.headerSub}>हिंदी में उत्तर</Text>
        </View>
        <Pressable onPress={clear} style={styles.backBtn} testID="clear-chat">
          <Ionicons name="trash-outline" size={20} color={colors.muted} />
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <FlatList
          ref={listRef}
          data={msgs}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: 16, gap: 10 }}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          renderItem={({ item }) => (
            <View style={[styles.bubbleWrap, item.role === "user" ? { alignItems: "flex-end" } : { alignItems: "flex-start" }]}>
              <View
                style={[
                  styles.bubble,
                  item.role === "user"
                    ? { backgroundColor: colors.brandPrimary }
                    : { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
                ]}
              >
                <Text style={{ color: item.role === "user" ? "#FFFFFF" : colors.onSurface, fontSize: 14, lineHeight: 20 }}>
                  {item.text}
                </Text>
              </View>
            </View>
          )}
        />
      )}

      <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
        <TextInput
          testID="chat-input"
          placeholder="अपना प्रश्न लिखें..."
          placeholderTextColor={colors.muted}
          value={input}
          onChangeText={setInput}
          style={styles.input}
          multiline
        />
        <Pressable
          onPress={send}
          disabled={sending || !input.trim()}
          style={[styles.sendBtn, { backgroundColor: colors.brandPrimary, opacity: sending || !input.trim() ? 0.6 : 1 }]}
          testID="send-chat"
        >
          {sending ? <ActivityIndicator color="#FFFFFF" /> : <Ionicons name="send" size={18} color="#FFFFFF" />}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors) => ({
  header: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingBottom: 12,
    backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 4,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 20 },
  headerTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  headerSub: { fontSize: 11, color: colors.muted },
  bubbleWrap: {},
  bubble: { maxWidth: "80%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16 },
  inputBar: {
    flexDirection: "row", alignItems: "flex-end", gap: 8, padding: 12,
    backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.border,
  },
  input: {
    flex: 1, minHeight: 44, maxHeight: 120, backgroundColor: colors.surfaceTertiary,
    borderRadius: 22, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 12,
    color: colors.onSurface, fontSize: 15,
  },
  sendBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
}));

import { Tabs } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { Platform } from "react-native";
import { useTheme } from "@/src/theme";
import { useBadges } from "@/src/hooks/useBadges";

export default function AdminLayout() {
  const { colors } = useTheme();
  const { badges } = useBadges();
  const pendingPayments = badges.pending_payments || 0;
  const badgeStyle = { backgroundColor: colors.error, color: colors.onError, fontSize: 10, fontWeight: "700" as const };
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary, borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="overview" options={{ title: "Overview", tabBarIcon: ({ color, size }) => <Ionicons name="stats-chart" color={color} size={size} /> }} />
      <Tabs.Screen name="subscribers" options={{ title: "Users", tabBarIcon: ({ color, size }) => <Ionicons name="people" color={color} size={size} /> }} />
      <Tabs.Screen name="team" options={{ title: "Team", tabBarIcon: ({ color, size }) => <Ionicons name="briefcase" color={color} size={size} /> }} />
      <Tabs.Screen
        name="payments"
        options={{
          title: "Payments",
          tabBarIcon: ({ color, size }) => <Ionicons name="wallet" color={color} size={size} />,
          tabBarBadge: pendingPayments > 0 ? pendingPayments : undefined,
          tabBarBadgeStyle: badgeStyle,
        }}
      />
      <Tabs.Screen name="complaints" options={{ title: "Tickets", tabBarIcon: ({ color, size }) => <Ionicons name="alert-circle" color={color} size={size} /> }} />
      <Tabs.Screen name="plans" options={{ href: null, tabBarStyle: { display: "none" } }} />
      <Tabs.Screen name="report" options={{ href: null, tabBarStyle: { display: "none" } }} />
    </Tabs>
  );
}

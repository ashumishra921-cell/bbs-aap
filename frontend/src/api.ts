import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import Constants from "expo-constants";

const BASE = Constants.expoConfig?.extra?.backendUrl ?? process.env.EXPO_PUBLIC_BACKEND_URL;

export type Role = "subscriber" | "team" | "admin" | "super_admin";
export type PaymentHistoryItem = {
  id: string; invoice_id: string | null; user_id: string; user_name: string;
  user_phone: string; plan_name: string; amount: number; payment_mode: string;
  status: string; created_at: string; reject_reason: string | null;
};
export type ActivityItem = { key: string; version: string; kind: "complaint" | "payment"; title: string };
export type User = {
  id: string;
  phone: string;
  name: string;
  role: Role;
  address?: string;
  location?: { lat: number; lng: number; updated_at?: string | null; sharing?: boolean };
};

const TOKEN_KEY = "auth_token";
const USER_KEY = "auth_user";

export async function saveAuth(token: string, user: User) {
  await AsyncStorage.setItem(TOKEN_KEY, token);
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(user));
}

export async function loadAuth(): Promise<{ token: string | null; user: User | null }> {
  const token = await AsyncStorage.getItem(TOKEN_KEY);
  const raw = await AsyncStorage.getItem(USER_KEY);
  return { token, user: raw ? JSON.parse(raw) : null };
}

export async function clearAuth() {
  await AsyncStorage.multiRemove([TOKEN_KEY, USER_KEY]);
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await AsyncStorage.getItem(TOKEN_KEY);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/api${path}`, { ...options, headers });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      msg = data.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  const txt = await res.text();
  return txt ? JSON.parse(txt) : (undefined as unknown as T);
}

export const api = {
  authConfig: () =>
    request<{ sms_enabled: boolean; demo_otp: string | null; resend_cooldown_sec: number }>("/auth/config"),
  requestOtp: (phone: string) =>
    request<{ success: boolean; otp: string | null; mode: "demo" | "sms"; is_new_user: boolean }>("/auth/request-otp", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),
  verifyOtp: (phone: string, otp: string, name?: string) =>
    request<{ token: string; user: User }>("/auth/verify-otp", {
      method: "POST",
      body: JSON.stringify({ phone, otp, name }),
    }),
  me: () => request<User>("/auth/me"),
  deleteMyAccount: () => request("/auth/me", { method: "DELETE" }),
  badges: () => request<any>("/badges"),
  adminExpiring: (days = 3) => request<any[]>(`/admin/expiring?days=${days}`),

  plans: () => request<any[]>("/plans"),
  plansAll: () => request<any[]>("/plans?all=true"),
  createPlan: (p: any) => request<any>("/plans", { method: "POST", body: JSON.stringify(p) }),
  updatePlan: (id: string, p: any) => request<any>(`/plans/${id}`, { method: "PATCH", body: JSON.stringify(p) }),
  deletePlan: (id: string) => request<any>(`/plans/${id}`, { method: "DELETE" }),

  report: (month?: string) => request<any>(`/admin/report${month ? `?month=${month}` : ""}`),
  reminders: () => request<{ sms_enabled: boolean; items: any[] }>("/admin/reminders"),
  runReminders: () => request<any>("/admin/reminders/run", { method: "POST" }),

  updateMyLocation: (lat: number, lng: number) =>
    request<any>("/team/location", { method: "POST", body: JSON.stringify({ lat, lng, sharing: true }) }),
  stopMyLocation: () => request<any>("/team/location", { method: "DELETE" }),

  mySubscription: () => request<any | null>("/me/subscription"),

  paymentConfig: () => request<{ upi_id: string; payee_name: string }>("/payment-config"),
  uploadScreenshot: async (uri: string, name: string, type: string) => {
    const token = await AsyncStorage.getItem(TOKEN_KEY);
    const form = new FormData();
    if (Platform.OS === "web") {
      const blob = await (await fetch(uri)).blob();
      form.append("file", blob, name);
    } else {
      form.append("file", { uri, name, type } as any);
    }
    const res = await fetch(`${BASE}/api/payments/upload-screenshot`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: form,
    });
    if (!res.ok) {
      let msg = `Upload failed (${res.status})`;
      try { msg = (await res.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    return (await res.json()) as { path: string };
  },
  fileUrl: (path: string, token: string | null) => `${BASE}/api/files/${path}${token ? `?token=${encodeURIComponent(token)}` : ""}`,
  createPayment: (b: { plan_id: string; screenshot_path: string; utr?: string }) =>
    request<any>("/payments", { method: "POST", body: JSON.stringify(b) }),
  payments: () => request<any[]>("/payments"),
  approvePayment: (id: string) => request<any>(`/payments/${id}/approve`, { method: "POST" }),
  rejectPayment: (id: string, reason?: string) =>
    request<any>(`/payments/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),

  invoices: () => request<any[]>("/invoices"),
  paymentHistory: (mode = "all", search = "", offset = 0, limit = 40) =>
    request<{ items: PaymentHistoryItem[]; has_more: boolean }>(`/payment-history?mode=${mode}&search=${encodeURIComponent(search)}&offset=${offset}&limit=${limit}`),
  activity: () => request<ActivityItem[]>("/activity"),
  invoice: (id: string) => request<any>(`/invoices/${id}`),

  complaints: () => request<any[]>("/complaints"),
  settings: () => request<{ auto_assign: boolean }>("/settings"),
  updateSettings: (b: { auto_assign: boolean }) =>
    request<{ auto_assign: boolean }>("/settings", { method: "PATCH", body: JSON.stringify(b) }),
  createComplaint: (b: { title: string; description: string; priority?: string; lat?: number; lng?: number }) =>
    request("/complaints", { method: "POST", body: JSON.stringify(b) }),
  updateComplaint: (id: string, b: any) =>
    request(`/complaints/${id}`, { method: "PATCH", body: JSON.stringify(b) }),

  team: (lat?: number, lng?: number) =>
    request<any[]>(`/team${lat != null && lng != null ? `?lat=${lat}&lng=${lng}` : ""}`),
  createTeam: (b: { phone: string; name: string; role: string }) =>
    request("/team", { method: "POST", body: JSON.stringify(b) }),
  deleteTeam: (id: string) => request(`/team/${id}`, { method: "DELETE" }),

  subscribers: () => request<any[]>("/subscribers"),
  createSubscriber: (b: Record<string, any>) =>
    request<any>("/subscribers", { method: "POST", body: JSON.stringify(b) }),
  updateSubscriber: (id: string, b: Record<string, any>) =>
    request<any>(`/subscribers/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  assignPlan: (id: string, plan_id: string, payment_mode: string) =>
    request<any>(`/subscribers/${id}/assign-plan`, { method: "POST", body: JSON.stringify({ plan_id, payment_mode }) }),
  deleteSubscriber: (id: string) => request(`/subscribers/${id}`, { method: "DELETE" }),
  adminMetrics: () => request<any>("/admin/metrics"),

  chat: (message: string) => request<{ reply: string }>("/chat", { method: "POST", body: JSON.stringify({ message }) }),
  chatHistory: () => request<any[]>("/chat/history"),
  clearChat: () => request("/chat/history", { method: "DELETE" }),
};

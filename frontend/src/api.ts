import AsyncStorage from "@react-native-async-storage/async-storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export type Role = "subscriber" | "team" | "admin" | "super_admin";
export type User = {
  id: string;
  phone: string;
  name: string;
  role: Role;
  address?: string;
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

  plans: () => request<any[]>("/plans"),
  createPlan: (p: any) => request("/plans", { method: "POST", body: JSON.stringify(p) }),
  deletePlan: (id: string) => request(`/plans/${id}`, { method: "DELETE" }),

  mySubscription: () => request<any | null>("/me/subscription"),
  recharge: (plan_id: string, upi_id: string) =>
    request("/recharge", { method: "POST", body: JSON.stringify({ plan_id, upi_id }) }),

  invoices: () => request<any[]>("/invoices"),
  invoice: (id: string) => request<any>(`/invoices/${id}`),

  complaints: () => request<any[]>("/complaints"),
  settings: () => request<{ auto_assign: boolean }>("/settings"),
  updateSettings: (b: { auto_assign: boolean }) =>
    request<{ auto_assign: boolean }>("/settings", { method: "PATCH", body: JSON.stringify(b) }),
  createComplaint: (b: { title: string; description: string; priority?: string }) =>
    request("/complaints", { method: "POST", body: JSON.stringify(b) }),
  updateComplaint: (id: string, b: any) =>
    request(`/complaints/${id}`, { method: "PATCH", body: JSON.stringify(b) }),

  team: () => request<any[]>("/team"),
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

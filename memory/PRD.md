# Broadband Solutions 24×7 — PRD

## Overview
Local Internet Service Provider (ISP) management mobile app (Expo React Native + FastAPI + MongoDB) with 4 roles: Super Admin, Admin, Team Member, Subscriber.

## Roles & Flows
- **Subscriber**: Phone/OTP signup → dashboard (active plan, data usage, expiry) → recharge plans (mock UPI) → register/track complaints → view invoices → AI chatbot (Hindi).
- **Team Member**: Phone/OTP login (must be pre-seeded by admin) → view assigned tickets → update status (in_progress / resolved) with resolution note.
- **Admin**: Metrics dashboard (subscribers, revenue, tickets) → manage subscribers list → manage team (create/delete team members) → view all complaints & assign to team.
- **Super Admin**: Same as Admin + can create/delete Admin users.

## Key Features
- Multi-role phone/OTP auth (mocked OTP `123456`).
- Plans catalog with mock UPI payment → auto-generates invoice + activates subscription.
- Complaint ticketing with priority (low/med/high), status flow (open → assigned → in_progress → resolved).
- AI Chatbot in Hindi via Claude Haiku 4.5 (Emergent LLM key).
- Invoice detail view with billing info.

## Tech Stack
- Frontend: Expo Router 57, React Native 0.86, react-native-reanimated, expo-linear-gradient, @react-native-vector-icons/ionicons.
- Backend: FastAPI + Motor (MongoDB async) + emergentintegrations for Claude Haiku.
- Design: Teal/blue palette (`#0F766E` primary), clean cards, iOS-native clean personality.

## Seeded Data
- 4 role users (see test_credentials.md).
- 4 broadband plans (₹499 / ₹799 / ₹1199 / ₹1599).

## Helpline
- Customer helpline 8826004211 shown as tap-to-call card on subscriber Home & Profile (src/components/HelplineCard.tsx).

## SMS OTP + WhatsApp (added)
- Backend supports MSG91 OTP (send `POST control.msg91.com/api/v5/otp`, verify `GET /api/v5/otp/verify`). Env: MSG91_AUTH_KEY, MSG91_TEMPLATE_ID, MSG91_DLT_TE_ID, DEMO_NUMBERS, DEMO_OTP. Falls back to demo OTP for all numbers when keys are empty.
- Phone normalization (+91/0 prefix), 30s resend cooldown for real SMS, `GET /api/auth/config`.
- OTP screen: mode-aware subtitle + "OTP फिर से भेजें" resend button with 30s countdown.
- HelplineCard: Call + WhatsApp (wa.me/918826004211) buttons on subscriber Home & Profile.

## Subscriber management (Super Admin only)
- `POST /api/subscribers` {phone,name,address?} and `DELETE /api/subscribers/{id}` — require_role("super_admin"); delete also removes their subscriptions & complaints.
- Admin "Users" tab: add FAB + bottom-sheet form and per-row delete (with confirm) visible only to super_admin; admin/team see read-only list.

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

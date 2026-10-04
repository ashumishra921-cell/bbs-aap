# Broadband Solutions 24×7 — PRD

## Product
Mobile ISP management app for Super Admin, Admin, Team Members and Subscribers. Core flows: phone/OTP login, plans and subscriptions, UPI screenshot payments/invoices, complaints and assignment, Hindi AI support chat, payment history, expiry awareness, live refresh and dashboard alerts.

## Architecture
- **Mobile:** Expo Router / React Native, TypeScript, Expo Audio, AsyncStorage, Expo Image.
- **Backend:** FastAPI, Motor/MongoDB, JWT auth, Emergent Object Storage for payment images.
- **Integrations:** Emergent LLM for Hindi chatbot; MSG91 is the intended production OTP provider after DLT/template setup. Traccar gateway is disabled.

## Implemented
- Role-scoped dashboards, subscriptions, plan management, customer/team management, UPI screenshot review, invoices, reports and payment history.
- Complaint creation, automatic/administrative assignment, team work states, location sharing and status updates.
- Foreground complaint and payment audio alerts with a visible switch, test controls and ~9-second repeat/automatic-stop playback.
- Subscriber Home refreshes while focused so new plan activations become visible without manual navigation.
- UPI files are stored in managed object storage and accessed using Authorization bearer headers only.

## Security Status — Iteration 11
- Production authentication is **real-provider-only**: public demo OTP, shared `123456`, role bypasses and seeded privileged demo accounts are disabled.
- If no configured secure SMS provider exists, request/verify OTP fail closed with a non-sensitive 503. Current MSG91 credentials are not yet configured, so public login is intentionally unavailable.
- OTP endpoints have phone + hashed-IP throttles; responses never return an OTP.
- JWTs require `exp` + `jti`, expire after `JWT_TTL_MINUTES`, and logout stores a server-side revocation record. Legacy non-expiring tokens are rejected.
- Team members cannot access other users' invoices. File query-token access is rejected. CORS is strict in FastAPI, credentials are disabled, and standard security headers are attached.
- Independent Iter11 regression passed: **10/10 backend** and **2/2 frontend** security checks.

## Known Infrastructure Limitation
- The public preview ingress/proxy still alters CORS: local FastAPI preflight honors the exact allowlist, but the preview layer injects wildcard GET headers and rejects OPTIONS before app code runs. Keep the app allowlist strict; upstream proxy configuration needs correction.

## Backlog
- **P0:** Configure MSG91 Auth Key, OTP Template/Flow ID and DLT Template ID; then test a real non-privileged customer OTP flow.
- **P0:** Correct preview ingress/proxy CORS mutation without weakening app CORS.
- **P1:** Optional collection reporting, extended technician/location validation and plan-editor verification.
- **P2:** Closed-app push notifications for complaint assignments/status changes.
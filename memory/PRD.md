# Broadband Solutions 24×7 — PRD

## Product
Mobile ISP management app for Super Admin, Admin, Team Members and Subscribers. Core flows: phone/OTP login, plans and subscriptions, UPI screenshot payments/invoices, complaints and assignment, Hindi AI support chat, payment history, expiry awareness, live refresh and dashboard alerts.

## Current Problem Statement
Customer creation must reliably capture ISP User ID, ISP provider and optional manual expiry; subscribers must clearly see and upgrade their active plan; AI Support must expose the 8826004211 call action; Super Admin must be able to add customers in bulk.

## Architecture
- **Mobile:** Expo Router / React Native, TypeScript, Expo Audio, AsyncStorage, Expo Image.
- **Backend:** FastAPI, Motor/MongoDB, JWT auth, Emergent Object Storage for payment images.
- **Integrations:** Emergent LLM for Hindi chatbot; WhatsBoost is the configured WhatsApp OTP and transactional-notification provider. Traccar and MSG91 are not used for OTP.

## Implemented
- Role-scoped dashboards, subscriptions, plan management, customer/team management, UPI screenshot review, invoices, reports and payment history.
- Customer creation now supports unique ISP User ID, Anonet/Zepbyt/GTPL or custom provider, optional plan activation, manual expiry and clear inline validation. Legacy plans without an explicit `active` field remain assignable unless disabled.
- Super Admin bulk customer import accepts up to 200 pasted CSV-style rows with mobile preview, validation summary and per-row backend results; other roles are denied.
- Subscriber Home displays an explicit ACTIVE plan card and Upgrade / Change Plan action leading to the recharge plan list.
- AI Support displays human support number 8826004211 with a one-tap phone dial action.
- Native login sessions are encrypted in SecureStore, migrate once from AsyncStorage, validate against `/auth/me` at startup, and remain valid for 30 days unless expired, revoked or logged out.
- A lightweight `/api/health` check runs on app start/resume and every four active minutes; transient GET failures use bounded retries so a waking backend reconnects without duplicate POST actions.
- Admin/Super Admin daily collection entry: both can add subscribers, record Cash or UPI payment, and activate a plan immediately. UPI requires an actor-owned screenshot (UTR optional); Cash uses a no-screenshot payment record and is shown safely in Payments.
- Pending Balance: Subscriber Home shows ₹0 clear state or the latest expired-plan renewal amount with a Recharge action; Admin Collection Report provides the customer-wise Pending Balance follow-up list.
- Complaint creation, automatic/administrative assignment, team work states, location sharing and status updates.
- Foreground complaint and payment audio alerts with a visible switch, test controls and ~9-second repeat/automatic-stop playback.
- Subscriber Home refreshes while focused so new plan activations become visible without manual navigation.
- UPI files are stored in managed object storage and accessed using Authorization bearer headers only.
- WhatsBoost sends login OTP plus plan activation, payment submission/confirmation, complaint updates and expiry reminders. Login codes are server-side hashed, six digits, five-minute expiry and five-attempt maximum; transaction messages are idempotent by business event and never roll back core business actions. Subscriber WhatsApp updates default ON and can be switched OFF from Profile.
- Expiry reminders use approved WhatsBoost template `6ac1fddef3f1df9b9465836c` on the IST calendar date exactly two days before plan expiry. Mapping: `{1}` subscriber name, `{2}` expiry date, `{3}` current plan billing amount. Generic/SMS expiry dispatch is not used by the active scheduler.

## Security Status — Iteration 11
- Production authentication is **real-provider-only**: public demo OTP, shared `123456`, role bypasses and seeded privileged demo accounts are disabled.
- WhatsBoost-only OTP fails closed when backend credentials are absent; it has no MSG91 or Traccar fallback.
- OTP endpoints have phone + hashed-IP throttles; responses never return an OTP.
- JWTs require `exp` + `jti`, expire after `JWT_TTL_MINUTES`, and logout stores a server-side revocation record. Legacy non-expiring tokens are rejected.
- Super Admin phone migrations preserve the immutable Super Admin user id, archive a conflicting empty target account rather than deleting data, invalidate OTP challenges, block the retired number from OTP, and reject archived-account sessions.
- Team members cannot access other users' invoices. File query-token access is rejected. CORS is strict in FastAPI, credentials are disabled, and standard security headers are attached.
- Independent Iter11 regression passed: **10/10 backend** and **2/2 frontend** security checks.

## Known Infrastructure Limitation
- The public preview ingress/proxy still alters CORS: local FastAPI preflight honors the exact allowlist, but the preview layer injects wildcard GET headers and rejects OPTIONS before app code runs. Keep the app allowlist strict; upstream proxy configuration needs correction.

## Backlog
- **P0:** Rotate the WhatsBoost credentials shared in chat, update backend-only `WHATSBOOST_APPKEY`/`WHATSBOOST_AUTHKEY`, then run one manual OTP and opted-in transaction-message check with an explicitly consented recipient. Provider HTTP acceptance is not a delivery receipt.
- **P0:** Correct preview ingress/proxy CORS mutation without weakening app CORS.
- **P1:** Optional collection reporting, extended technician/location validation and plan-editor verification.
- **P2:** Closed-app notification sounds await Firebase `google-services.json`; planned routing is Admin/Super Admin (payment + complaint), Team (assigned complaint), and Subscriber (own relevant updates).
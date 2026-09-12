# Broadband Solutions 24×7 — PRD

## Overview
Local Internet Service Provider (ISP) management mobile app (Expo React Native + FastAPI + MongoDB) with 4 roles: Super Admin, Admin, Team Member, Subscriber.

## Roles & Flows
- **Subscriber**: Phone/OTP signup → dashboard (active plan, data usage, expiry) → UPI screenshot recharge awaiting Super Admin approval → register/track complaints → view payment history/invoices → AI chatbot (Hindi).
- **Team Member**: Phone/OTP login (must be pre-seeded by admin) → view assigned tickets → update status (in_progress / resolved) with resolution note.
- **Admin**: Metrics dashboard (subscribers, revenue, tickets) → manage subscribers list → manage team (create/delete team members) → view all complaints & assign to team.
- **Super Admin**: Same as Admin + can create/delete Admin users.

## Key Features
- Multi-role phone/OTP auth (mocked OTP `123456`).
- Plans catalog with UPI screenshot payment → Super Admin approves → invoice + subscription. Existing Super Admin manual plan assignment supports Cash/UPI/Free.
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

## Deployment
- Root-level GET / and GET /health (plus /api/health) return 200 for platform health probes.

## Complaint automation (fix: technicians saw no tickets)
- New complaints auto-assign to the least-loaded technician (status=assigned, auto_assigned=true). Admin toggle: GET/PATCH /api/settings {auto_assign} (stored in db.settings), Switch on admin Tickets screen.
- Technicians now see own tickets + unassigned open tickets; can "Accept Ticket" (self-claim via PATCH assigned_to=self). Team screen has NEW / ACTIVE / RESOLVED segments.

## Iteration 5 (user-reported)
- Admin/Super Admin can Close (resolve) / Reopen tickets from admin Tickets sheet with optional note.
- Overview: crash-guard when metrics fail (error + Retry), metric cards tappable → navigate to Users/Team/Tickets tabs, pull-to-refresh.
- Subscriber details: User model + router_model, router_mac, security_deposit, installation_date, notes. PATCH /api/subscribers/{id} (edit), POST /api/subscribers/{id}/assign-plan {plan_id, payment_mode cash|upi|free} (shared activate_plan() also used by /recharge; Invoice.payment_mode added). Create form can activate a plan immediately.
- Users tab: search bar (name/phone/address), detail sheet (Assign/Renew Plan, Edit, Delete for super_admin).
- Timing fix: Mongo client tz_aware=True → all datetimes serialize with +00:00 so the app shows correct local (IST) time.

## UPI payment with screenshot verification (replaces mock instant recharge)
- UPI_ID=9312004211-2@ybl, UPI_PAYEE_NAME in backend/.env → GET /api/payment-config.
- Subscriber Recharge: plan → sheet with UPI QR (upi://pay deep link), UPI ID copy, "Pay via UPI app" (native), screenshot picker (expo-image-picker w/ permission flow + Open Settings), optional UTR → POST /api/payments/upload-screenshot (multipart → Emergent Object Storage, path broadband-solutions-247/uploads/{uid}/{uuid}.ext, meta in db.files) → POST /api/payments (pending). One pending per user. "My Payments" history with status.
- Admin "Payments" tab: list pending/all with screenshot thumbnails (GET /api/files/{path}?token= for web, Authorization header on native). Super Admin only: Approve (activate_plan → invoice+subscription, payment_mode upi, utr) / Reject with reason. Admin can view only.
- POST /api/recharge now returns 410 (instant mock disabled).

## Alerts, expiry reminders, delete account
- GET /api/badges (role-aware): team {new_tickets}, admin/super {pending_payments, open_tickets, expiring_soon}, subscriber {expiring_soon, days_left}. Frontend hook src/hooks/useBadges.ts polls every 30s (foreground only) → tabBarBadge on Team "Tickets" and Admin "Payments" tabs.
- GET /api/admin/expiring?days=3 → subscribers whose active plan expires within N days; shown on Admin Overview "Expiring in 3 days" card (tap row = call). Subscriber Home shows amber/red expiry banner when ≤3 days left (tap → Recharge).
- DELETE /api/auth/me → self-delete (super_admin blocked 403): removes user, subscriptions, pending payments, chat; anonymises invoices/complaints/payments; unassigns tickets. Profile: "Delete my account" with confirm (Alert native / modal web) → logout.

## Current increment: dashboard payments, foreground tones, plan refresh
- User chose ONLY dashboard UPI shortcut, payment history and sound alerts. No new cash-entry flow; earlier four unfinished features explicitly deferred.
- Reported bug: Super Admin plan activation not visible in subscriber app. RCA found backend correct, Home refreshed only on navigation. `useLiveRefresh` now refreshes Home while focused every 10s and on app resume, with error/retry UI retaining previous data.
- `/api/payment-history`: role-scoped, paginated unified invoice/payment-request ledger. All/UPI/Cash/Free filter, literal search, approval receipt deduplication; subscribers only see own records, admins all customers. New response models in `backend/payment_activity.py` exclude BSON IDs.
- Dashboard `PaymentDashboardCard`: UPI shortcut (subscriber recharge / admin review queue), UPI ID copy, full payment history shortcut. `/payment-history` screen shows mode, amount, status, date, customer name/phone for admins, invoice links. Invoice detail displays payment mode.
- `/api/activity`: role-scoped complaint/payment ID+version snapshots. `ActivityAlertsProvider` polls every 10s while foreground; first fetch silent; unchanged polls silent, per-user persisted mute setting. Bundled original complaint/payment WAVs use expo-audio. Test-tone buttons and latest alert shown on dashboards/team Profile.
- No microphone, recording, background audio, or push capabilities added. Sound while app closed is not implemented; real-device speaker/silent-mode behavior needs device validation.
- Frontend Expo config exposes backend URL via `Constants.expoConfig.extra.backendUrl`, sourced from existing environment variable. Protected Metro/env settings unchanged.
- Verification COMPLETE for requested scope: iter8 10/11 backend checks passed, failed role fixture repaired and passed recheck in iter9; iter9 focused backend3/3 plus requested UI flows passed. Live plan update without navigation, automatic complaint/payment audio events, silent initial/unchanged snapshots, mute persistence/account isolation, subscriber-local updates, team scope, admin/super permissions, history filters/search/invoice modes all verified. Modal verified390x844 and320x700. Native speaker behavior still requires a phone check.
- Iter9 optional follow-ups addressed: sound ON/OFF indicator and checked accessibility state; payment screenshot rendering waits for token. Final self-test observed real image pixels and3/3 authenticated file responses HTTP200 (no401 observed).
- Existing Recharge modal made phone-height constrained with internal scroll, fixed submit/cancel footer and top close. Documented Admin/Team demo test fixtures restored by explicit exact-ID operator script, not via login/startup privileges; both API role logins verified.

## Backlog
- P0: None remaining in requested scope. Phone sound/volume confirmation recommended for device-specific behavior.
- P1 (deferred by user): Prior Expiry SMS, Collection Report, Technician Location and Plan Editor end-to-end verification; prior report.tsx hook warning. SMS requires MSG91 credentials/templates; no SMS delivery verified.
- P2: Closed-app push notifications; optional new cash-entry flow only if requested.

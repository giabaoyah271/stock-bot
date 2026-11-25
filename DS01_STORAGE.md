# DS01 — Persistent Data Storage (test branch)

Source baseline: 88fe73ab19e5707e496cb3a086bdd83be195c0ce. No engine or JSON schema change.
Dedicated Supabase project, private Streamlit app, one owner only. Do not expose publicly or use for multiple users.
No secrets, data archives or actual accounts are included. Cloud integration requires manual acceptance.

## Architecture
The two version/head tables cover the reference, Paper, scan, standalone PT10 and preferences
kinds. This generic schema replaces six proposed entity-specific tables. The sync log is separate.
Bytes are immutable objects named namespace/kind/sha256. A database RPC checks the expected
version under a transaction-level advisory lock, then commits the next head. Upload/SQL are
not one transaction; failed uploads/commits may leave orphan objects, never a new active head.
Identical content deduplicates. A timeout is resolved only if the current head matches the exact SHA.
All Paper writes commit before session update. Restored reports are view-only until a new main
scan; old timestamp is never changed. A fresh main scan does not merge recovered batches.
Only main scanner reports and validated daily standalone PT10 are persisted; advanced PT02
TEST and auxiliary 1H/Week remain session-only. Preferences use an explicit allowlist.
No persisted TCBS credentials, OTP, submit confirmation or broker orders.

## Setup — free test project
1. Create a **new** Supabase project under your account, select Free. Do not share keys in chat.
2. Open SQL Editor, paste and run [001_ds01.sql](supabase/migrations/001_ds01.sql).
   Verify Storage > stock-bot-private is Private; no public or broad custom storage policies.
3. Authentication > Users: create one confirmed email/password user, copy its UUID.
   Disable new user signup in Authentication settings. Use a unique strong password.
4. Project Settings > API Keys: use legacy anon and service_role keys for the documented
   JWT REST flow. The service_role key is highly privileged; use it only in server Secrets.
5. Create a separate **private** Streamlit app on branch feature/persistent-storage, app.py,
   Python 3.11, copy existing TCBS Secrets privately. Add the following in Secrets:

```toml
[supabase]
url = "https://YOURPROJECT.supabase.co"
anon_key = "YOUR_LEGACY_ANON_KEY"
service_role_key = "YOUR_LEGACY_SERVICE_ROLE_KEY"
owner_id = "YOUR_AUTH_USER_UUID"
namespace = "ds01-test"
market_storage_allowed = false
```

6. Login at app's Supabase Auth screen. The app checks the configured owner UUID; session
   authorization expires after one hour and on reload. It does not retain passwords or JWTs.
   Service-role access is gated by this server-side check; RLS blocks anon/authenticated direct DB access.
   This is not a multi-tenant implementation. Production must use a different project and Secrets.
7. With market_storage_allowed=false, verify connection and preference persistence, no TCBS-derived
   bytes are uploaded. Confirm your source license/TCBS agreement permits external private storage
   of U5-B, derived reports and Paper data. Only then set market_storage_allowed=true in Secrets.
   Use synthetic fixtures for testing until permission is confirmed.
8. In Hệ thống > Thiết lập & sao lưu, upload exact U5-B and verify. Restore your JSON Paper
   only after backing it up locally. Never create a new account instead of restoring an existing one.
   Confirm statuses in Lưu trữ & đồng bộ. Scan freshly, inspect and explicitly record only an eligible session.
9. Reload, login again, verify U5-B, account, reports, chart and preferences. Reboot and repeat.
   Test a second browser: stale Paper version must be rejected. Do not test duplicate production
   trades; use an isolated test account. Download old snapshot and confirm import validation.

## Limits and failures
Free plan currently advertises 1 GB file storage, 500 MB DB and max 50 MB upload.
App caps each object at 47 MiB; standard upload only, reports gzip JSON with bounded decode.
No actual U5-B/115-chart sizes measured. Large files may require resumable upload or chunking later.
Project may pause after inactivity. Cloud errors must not be mistaken for missing data.
Reference/scan may remain available in session after failed save; Paper writes with storage enabled
are blocked until the current Cloud version is loaded and the new write confirmed.
In the absence of any Supabase configuration, original manual session workflow remains.
The UI shows usage on demand based on object metadata and 80/95% warnings against Free storage;
the dashboard is authoritative for billing/limits. No auto-upgrade or auto-deletion.
All versions retained initially; manual review before pruning. Proposed 30 latest Paper/7 scan days,
monthly pins, orphan cleanup and resumable upload are not automated by this version.
Download private JSON independently. Snapshots are not cryptographic signatures or offsite backup.
For rollback, revert deployment to research-v3 and import the latest validated local JSON and U5-B.
Do not delete the Supabase project or data before backup/verification.

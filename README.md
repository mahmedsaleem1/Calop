# Calop

Calop is a food scale. An ESP32-S3 CAM weighs your food and photographs it, AI identifies the food, and the server calculates nutrition from the **real weight** using only the *Food Composition Table for Pakistan*. You can also log food with the phone camera and a weight estimate. Each user answers a questionnaire once, sets a weight goal, and tracks daily intake against a calculated target.

This repo contains the **backend** (`calop-backend/`, FastAPI). The ESP32 firmware and the Expo app are separate projects; sections 5 and 6 tell you exactly how they must talk to this server.

```
Device or phone ── photo (+ weight) ──▶ server
                                          │ saves photo to local disk, capture to DB, queues 2 jobs, replies 202
                                          ├─ job A: AI recognition (Gemini by default)
                                          └─ job B: upload photo to Cloudinary, then delete the local file
confidence ≥ 0.90 on a valid food ─▶ logged automatically
otherwise                          ─▶ "needs review": top-3 candidates + table search, or discard
nutrition = amount per 100 g × weight ÷ 100  (reference table only, nothing estimated)
every status change ─▶ pushed to the app over WebSocket; the device polls for status
```

---

## 1. Project status

### Done (implemented and verified)

All 12 phases of `implementation.md` are implemented.

| Area | What exists |
|---|---|
| Foundations | Typed settings, error shape `{"error": {"code","message","request_id"}}`, `X-Request-ID`, `/api/v1` prefix, event log written in the same transaction as each change |
| Database | New baseline migration + 21 models (users, goals, targets, devices, captures, recognition runs/candidates, jobs, log entries, food tables, events) with the partial unique indexes, check constraints and cascades from the spec |
| Reference data | Extraction script (224 foods / 15 groups / 19 nutrients, fails on any surprise), hand-maintained `curation.csv` + `aliases.csv`, idempotent seed with full validation and `energy_mismatch` flags (19 foods) |
| Food search | Exact then trigram-fuzzy search, `roti`→Chapati, `biriyani`→Biryani, search-miss log, food detail, nutrition for a weight |
| Users | Questionnaire (once), 18+ check, weight history, goal replace, Mifflin–St Jeor target with 1 kg/week clamp, calorie floor, suggested dates, macro split, auto "goal achieved" |
| Devices | One active device per user, hashed keys, rotate, revoke (captures stay) |
| Capture ingest | Device and phone routes, idempotent retries, JPEG check, size limits, GPS EXIF stripped from phone photos without re-encoding, atomic file write, clock sanity check |
| Worker | Postgres job queue (`SKIP LOCKED`), retries with the specified delays, crash recovery, Cloudinary upload job, AI recognition job with stored raw responses |
| AI | Provider-neutral `FoodRecognizer` interface + one OpenAI-compatible implementation (Gemini by default). Switching provider = changing `VISION_AI_*` |
| Logging | auto / user-selected / "Wrong food?" correction, phone weight edit, discard, reprocess, delete (cascades; local file and Cloudinary image removed) |
| Realtime | `WS /api/v1/ws` with auth message, `capture.updated`, `capture.deleted`, ping/pong; device status polling |
| Reports | Daily (totals with per-nutrient coverage, remaining, estimated-entry count) and weekly (7 days, averages, weights, goal) aggregated in SQL |
| Tests | 37 unit tests (`pytest`, no database or network) |

**How it was verified.** The unit tests pass. In addition the whole pipeline was exercised end to end (83 checks) against a throwaway local PostgreSQL with a fake AI and fake Cloudinary: onboarding, device pairing, device capture → auto-log, retry idempotency, PNG rejected, GPS stripping (pixels identical), phone capture without weight → `awaiting_weight` → PATCH → logged, "Wrong food?", low confidence → review → select, not-in-catalog, reprocess, AI failure → `failed` after retries, Cloudinary failure → `upload_failed` keeps the local file, daily/weekly reports, WebSocket messages, delete with cascade, key rotation and revoke. The generated migration produces exactly the schema the models describe.

### Not verified yet (needs your environment)

I could not do these from the development machine, so run them once:

1. **Reset and migrate your Supabase database.** `alembic downgrade base` was blocked in my session, so I did **not** touch your database. Do it yourself with the commands in section 2.
2. **Real Gemini call: done.** `gemini-3.5-flash-lite` recognised an apple at 0.95 confidence and auto-logged it (about 4 s per call, 3.7k input tokens). `gemini-2.5-flash` and `gemini-3.5-flash` also worked; `gemini-2.5-flash-lite` is closed to new users. Only synthetic images were tried, so test a real roti photo.
3. **A real Cloudinary upload/delete** (the existing integration is unchanged, but it is now called from the worker).
4. **`alembic check` and `pg_trgm` on Supabase.** The local test database had no `pg_trgm`, so fuzzy search was tested with an SQL stand-in for `similarity()`. Supabase supports the extension; if `CREATE EXTENSION` is rejected, enable `pg_trgm` under Database → Extensions and rerun the migration.
5. **Real firmware and app** (not in this repo).

### Remaining

* The items above.
* **Later phases (out of scope by design):** multi-item plates (drop `UNIQUE(capture_id)` on log entries), AI nutritionist assistant, deficiency insights and micronutrient targets, account export/deletion, push notifications, cloud deployment, HTTPS.
* **Growing the food table:** foods not in the workbook cannot be logged. Add them to the workbook source, rerun the extraction, edit `curation.csv` / `aliases.csv`, reseed. `food_search_misses` shows what users looked for and did not find.
* **Firmware and Expo app** must be built to the contracts in sections 5 and 6.

### Deliberate small deviations from the spec

* `FoodRecognizer.recognize(image, catalog_text, system_prompt)` takes the prompt as a third argument, because the prompt constant lives in `recognition_service.py` and the integration may not import services.
* The health check moved to `GET /api/v1/health` (every router is under `/api/v1`).
* Signup's "confirm your email" reply is `{"message": ...}` instead of `{"detail": ...}`.
* If a goal's target date passes, the target falls back to maintenance and the response carries a `goal_expired` warning with a suggested date (instead of failing the recalculation).
* Weekly `averages` are over days that have logged entries (`days_logged` tells you how many), so a half-finished week is not dragged down by empty days.
* Dependency: SQLAlchemy is pinned `<2.1`.

---

## 2. Setup

```bash
cd calop-backend
python -m venv .venv && source .venv/Scripts/activate     # Windows Git Bash; use .venv\Scripts\activate in cmd
pip install -r requirements-dev.txt
cp .env.example .env                                      # then fill it in
```

`.env` needs the Supabase, Cloudinary and AI values (see `.env.example`). The AI model id must be a vision-capable model from your provider's model list; the default base URL is Gemini's OpenAI-compatible endpoint.

### Reset the dev database and load the food data (once)

All current data is dummy. This drops every Calop table (old ones too, e.g. `analyses`) in the database `DATABASE_URL` points to; Supabase Auth users are untouched.

```bash
python scripts/reset_dev_database.py --yes   # prints the database host first
alembic upgrade head                         # creates the new schema (enables pg_trgm)
alembic check                                # must report no differences
python -m app.seeds.reference                # Seeded: 224 foods, 15 groups, 19 nutrients, ...
python -m app.seeds.reference                # run twice: same result
pytest                                       # unit tests
```

### Run the server on your LAN

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000     # ONE process: do not use --workers
```

* Give your laptop a **reserved/static LAN IP** (router DHCP reservation), e.g. `192.168.1.50`. The firmware and the app both use `http://192.168.1.50:8000`.
* **Allow port 8000 in Windows Defender Firewall** (inbound, Private network), otherwise the phone and the ESP32 cannot reach the server.
* Interactive docs: `http://192.168.1.50:8000/docs`. Health: `/api/v1/health` (read the `db` field).
* Photos are stored in `calop-backend/storage/captures/` until Cloudinary confirms the upload, then deleted.

---

## 3. Everyday flow (what the user does)

1. Sign up / log in in the app, answer the questionnaire once (age, sex, height, weight, activity, diet, allergies, goal weight and date). The server returns a daily target and any warnings.
2. In the app, pair the scale: `POST /devices` returns an **API key once**. Put it in the firmware config and flash.
3. Put food on the scale. The device sends photo + weight; the OLED shows `SENDING`, then `LOGGED` / `CHECK APP` / `ERROR`.
4. If the AI is sure, the meal is logged. Otherwise the app shows the top-3 candidates + a search box + Discard.
5. Phone alternative: take a photo in the app, type an estimated weight (can be edited later).
6. "Wrong food?" on any entry changes only the food. Today / Week screens show intake vs target.

---

## 4. Quick test with `curl` (no hardware needed)

```bash
BASE=http://localhost:8000/api/v1
TOKEN=<access token from POST $BASE/auth/login>

# pair a device (key is shown once)
curl -s -X POST $BASE/devices -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"Kitchen scale"}'

# act as the ESP32
ID=$(python -c "import uuid;print(uuid.uuid4())")
curl -s -X POST $BASE/device/captures -H "X-API-Key: <device key>" -H "X-Firmware-Version: 0.1.0" \
     -F capture_id=$ID -F weight_g=182 -F image=@roti.jpg           # 202
curl -s $BASE/device/captures/$ID/status -H "X-API-Key: <device key>"  # {"status":"processing"} -> "logged"

# what the app sees
curl -s $BASE/captures/$ID -H "Authorization: Bearer $TOKEN"
curl -s "$BASE/reports/daily" -H "Authorization: Bearer $TOKEN"
```

---

## 5. Using it with your ESP32-S3 firmware

### Configuration (compile-time)

```
SERVER_URL      "http://192.168.1.50:8000"     // laptop's reserved LAN IP
API_KEY         "<key shown once when you paired the device in the app>"
FW_VERSION      "0.1.0"
```

### Loop

1. Connect to Wi-Fi. Show the live weight on the OLED.
2. When the weight is **stable and above 0**, capture a JPEG (full quality, **never resize or re-encode**; max 5 MB) and generate a **UUID v4** `capture_id`. Send whatever weight is on the scale (no tare logic needed).
3. `POST {SERVER_URL}/api/v1/device/captures` as `multipart/form-data`:

   | | |
   |---|---|
   | Headers | `X-API-Key: <key>`, `X-Firmware-Version: <ver>` |
   | Field `capture_id` | the UUID (required) |
   | Field `weight_g` | grams, `> 0` and `≤ 50000` (required for the device) |
   | Field `image` | the JPEG, filename ending `.jpg`, content type `image/jpeg` |
   | Field `captured_at` | optional ISO 8601 time; ignored by the server if the clock is off by more than 5 min ahead / 7 days behind |

   OLED: `SENDING`.
4. **Retry** on a network error or HTTP 5xx with the **same `capture_id`** (OLED `RETRY`). The server answers `200` with the stored capture, never a duplicate. Do not retry on 4xx.
5. On `200` or `202`, poll `GET {SERVER_URL}/api/v1/device/captures/{capture_id}/status` (same `X-API-Key`) every **500 ms for up to 15 s**:

   | Response `status` | OLED |
   |---|---|
   | `processing` | keep polling |
   | `logged` | `LOGGED` |
   | `needs_review` | `CHECK APP` |
   | `failed` | `ERROR` |
   | `discarded` | (stop) |
   | still `processing` at 15 s | `CHECK APP` |
6. Reuse one HTTP connection (keep-alive) across the upload and the polls.

### Error handling

Errors are JSON: `{"error":{"code":"...","message":"...","request_id":"..."}}`. Useful codes for the firmware:

| HTTP | `code` | Meaning |
|---|---|---|
| 401 | `invalid_api_key` | Key wrong, rotated or device revoked: re-pair in the app |
| 409 | `capture_id_in_use` | That UUID belongs to another user: generate a new one |
| 413 | `image_too_large` | Over 5 MB |
| 415 | `jpeg_required` | Not a JPEG |
| 422 | `invalid_capture_id` / `invalid_weight` | Bad UUID / weight ≤ 0 or missing |

Device weights are **measured**: they cannot be edited in the app. Only one device per user; re-pairing means revoking the old one first (or `rotate-key`).

---

## 6. Using it with your Expo (React Native) app

Base URL `http://<laptop LAN IP>:8000/api/v1`. Expo Go allows plain HTTP; **standalone builds must enable cleartext traffic** (Android `usesCleartextTraffic`, iOS ATS exception).

### Auth

* `POST /auth/signup`, `/auth/login`, `/auth/refresh` → `{access_token, refresh_token, expires_in, user}`. Signup may instead return `{message}` when email confirmation is on.
* Send `Authorization: Bearer <access_token>` on every call; refresh before `expires_in`. The server creates your `users` row on the first call.

### Startup

1. `GET /me` → if `onboarding_completed` is `false`, show the questionnaire.
2. `POST /me/onboarding` with `{date_of_birth, sex, height_cm, weight_kg, activity_level, diet_type, allergies, target_weight_kg, target_date}` (optional `timezone`, default `Asia/Karachi`). Response `{profile, goal, target, warnings}`. A warning (`goal_too_fast`, `calorie_floor`, `goal_expired`) never blocks: show its `suggested_target_date` and let the user resubmit with `PUT /me/goal`. Errors: `under_18` (must be 18+), `onboarding_already_completed`.
3. Open the WebSocket, then load pending work: `GET /captures?status=needs_review` and `GET /captures?status=awaiting_weight` (so missed messages never matter).

### Live updates

`WS ws://<host>:8000/api/v1/ws`. Send `{"type":"auth","token":"<access token>"}` within 5 s (otherwise close code `4401`); the server replies `{"type":"ready"}`. Then you receive:

* `{"type":"capture.updated","capture":{...}}` after every change to a capture, its image status or its entry
* `{"type":"capture.deleted","id":"..."}`

Send `{"type":"ping"}` to get `{"type":"pong"}`. Reconnect with back-off and reload the pending lists.

### Capture shape

```json
{"id":"…","source":"device","status":"needs_review","weight_g":182.0,"weight_source":"measured",
 "image_status":"uploaded","image_url":"/api/v1/captures/…/image","captured_at":null,"received_at":"…",
 "candidates":[{"code":"MAIN-19","display_name":"Chapati","confidence":0.71}],
 "not_in_catalog_label":null,"selected_food":null,"entry":null}
```

`status`: `identifying` → `logged` | `needs_review` | `awaiting_weight` | `failed` (| `discarded`). `entry` (when logged) = `{id, food, weight_g, weight_source, resolution, local_date, nutrients[{code,name,unit,amount}], missing[]}`. `missing` lists reported nutrients the table has no value for: show "not available", never 0.

### Phone capture

1. Take the photo with `expo-camera` as JPEG at full quality, no resizing, **no gallery import**. Generate a UUID.
2. `POST /captures` (multipart: `capture_id`, `image`, optional `weight_g`, optional `captured_at`; header `X-App-Version`). `202` new / `200` retry. Max 12 MB.
3. Ask for the weight while recognition runs, then `PATCH /captures/{id}` `{"weight_g": 250}` (works any time, also later to correct it; `409 weight_locked` for device captures). A capture with a food but no weight shows `awaiting_weight`.

### Review screen (`needs_review`)

Show `candidates`, a search box (`GET /foods?q=...` → `{match_type, items[{code,display_name,group,preparation_state,score}]}`), and **Discard**. Actions:

| Action | Call |
|---|---|
| Pick a food | `POST /captures/{id}/select` `{"food_code":"MAIN-19"}` |
| Discard | `POST /captures/{id}/discard` |
| Try the AI again | `POST /captures/{id}/reprocess` (from `failed` / `needs_review`) |
| Delete everything | `DELETE /captures/{id}` (204) |

If `not_in_catalog_label` is set, the AI saw a food that is not in the table: say so and offer search/discard. `GET /food-groups` + `GET /foods?group=...` let the user browse.

### Screens and endpoints

| Screen | Calls |
|---|---|
| Today | `GET /reports/daily?date=YYYY-MM-DD` → target, totals (with `entries_with_data`/`entries_total` coverage), remaining, entries, `estimated_entries` |
| Week | `GET /reports/weekly?week_start=YYYY-MM-DD` (Monday) |
| History | `GET /log-entries?from=&to=`, `PATCH /log-entries/{id}` `{"food_code"}` = **"Wrong food?"** (changes only the food) |
| Settings | `PATCH /me/profile`, `POST /me/weights`, `GET /me/weights`, `PUT /me/goal`, `GET /me/activity`, devices below |
| Device | `POST /devices` (key shown **once**), `GET /devices`, `PATCH /devices/{id}`, `POST /devices/{id}/rotate-key`, `DELETE /devices/{id}` (revokes; captures stay) |

Photos: load `GET /captures/{id}/image` **with the `Authorization` header** (it redirects to Cloudinary once uploaded, otherwise serves the local file). Recording a weight or changing the profile recalculates the target; reaching the goal weight marks the goal achieved and switches to a maintenance target.

All error bodies are `{"error":{"code","message","request_id"}}`; validation errors add `error.fields[{field,message,type}]`. Quote the `request_id` when reporting a bug: it is in the server log and in the `events` table.

---

## 7. Configuration reference

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | – | Supabase Postgres (session pooler, port 5432) |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | – | Auth |
| `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET` | – | Photo storage |
| `VISION_AI_API_KEY`, `VISION_AI_MODEL` | – | **Required.** Any vision model on an OpenAI-compatible API |
| `VISION_AI_BASE_URL` | Gemini OpenAI endpoint | Change with the provider |
| `VISION_AI_PROVIDER` | `gemini` | Label stored on each recognition run |
| `VISION_AI_REASONING_EFFORT` | `low` | Sent only if set |
| `VISION_AI_TIMEOUT_SECONDS` | `30` | |
| `VISION_AUTO_LOG_THRESHOLD` | `0.90` | At or above on a valid food → logged automatically |
| `LOCAL_IMAGE_DIR` | `storage/captures` | |
| `MAX_DEVICE_IMAGE_BYTES` / `MAX_PHONE_IMAGE_BYTES` | 5 MB / 12 MB | |
| `WORKER_THREADS` | `4` | |

## 8. Project layout

```
calop-backend/
  app/{controllers,services,models,views,integrations,core,seeds,migrations}/  worker.py realtime.py main.py
  data/reference/   source/*.xlsx  extracted/*.csv (generated)  curation.csv  aliases.csv (hand-edited)
  scripts/          extract_reference_data.py  reset_dev_database.py
  tests/            unit tests
  storage/          (gitignored) local photos awaiting upload
```

`CLAUDE.md` documents the architecture rules for contributors; `implementation.md` is the original specification.

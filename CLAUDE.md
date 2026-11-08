# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Calop is a food scale. An ESP32-S3 CAM weighs food and photographs it, AI identifies the food, and the server calculates nutrition from the real weight using only the Pakistan food composition table. Users can also log food with their phone camera and a typed weight estimate. The repo contains only the FastAPI service in `calop-backend/`; the firmware and the Expo app are separate. `README.md` has the user-facing guide, API summary and project status; `implementation.md` is the original build spec.

## Commands

Run everything from `calop-backend/`. `.env` and `alembic.ini` are found relative to the current directory, so commands fail from the repo root.

```
pip install -r requirements-dev.txt           # runtime + pytest + openpyxl
uvicorn app.main:app --host 0.0.0.0 --port 8000   # ONE process, no --workers (see below). Docs at /docs

alembic upgrade head                          # apply migrations (first line enables the pg_trgm extension)
alembic revision --autogenerate -m "message"  # create a migration from model changes
alembic check                                 # fail if the models and migrations differ
python scripts/reset_dev_database.py --yes    # drop every Calop table + alembic_version (dev database only)

python scripts/extract_reference_data.py      # xlsx -> data/reference/extracted/*.csv (generated, never hand-edited)
python -m app.seeds.reference                 # load the food tables (idempotent); restart the server afterwards
pytest                                        # unit tests: no database, no network
```

`.env` is gitignored; `calop-backend/.env.example` lists every variable. `app/core/config.py` requires `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `CLOUDINARY_*`, `VISION_AI_API_KEY` and `VISION_AI_MODEL`. Importing `app.main` or `app.core.database` reads the settings, so those imports fail if any are missing. Commands that use the database act on whichever one `DATABASE_URL` points to, which may be the real Supabase project.

The server must run as **one process**: the background worker and the WebSocket hub live in memory. `/api/v1/health` returns HTTP 200 even when the database is down, so read its `db` field.

SQLAlchemy is pinned `<2.1` because 2.1's compiled extension is blocked by Windows Application Control on the dev machine.

## Architecture

A request flows `controller → service → model / integration`, and the controller returns a view:

- `app/controllers/`: routes, plus the shared request dependencies in `dependencies.py`
- `app/services/`: business rules and all database queries
- `app/models/`: SQLAlchemy tables, one module per area (user, device, capture, food, log, job, event)
- `app/views/`: Pydantic request and response shapes
- `app/integrations/`: an interface and implementations for auth (Supabase), image storage (Cloudinary) and AI food recognition (`ai/`, any OpenAI-compatible API)
- `app/core/`: settings, database session, API key helpers, exceptions, request-id context, worker wake-up event
- `app/seeds/`: the food reference seed and the nutrient list shared with the extraction script
- `app/worker.py`, `app/realtime.py`: background job threads and the WebSocket hub
- `app/migrations/`: Alembic (one baseline migration)
- `data/reference/`: the source workbook, generated CSVs, and the hand-maintained `curation.csv` and `aliases.csv`

**Errors:** services raise the `ApplicationError` subclasses in `core/exceptions.py` (each has a `code`), which have no FastAPI dependency. `main.py` turns them, validation errors, HTTP errors and unhandled exceptions into `{"error": {"code", "message", "request_id"}}` (validation adds `error.fields`). The `request_id` is also the `X-Request-ID` response header. Don't raise `HTTPException` in services.

**Routes** all live under `/api/v1/...`.

**Two kinds of authentication** (`controllers/dependencies.py`):
- Users send `Authorization: Bearer <Supabase JWT>`, verified locally against Supabase's JWKS. The app's `users` row is created on the user's first authenticated request. `User.id` equals the Supabase user id but is deliberately not a foreign key to Supabase's auth schema.
- Devices send `X-API-Key` (and optionally `X-Firmware-Version`). Only the SHA-256 hash of the key is stored (`device_api_keys`), the plain key is returned once, and each authenticated request updates `last_used_at` / `last_seen_at`. One active device per user; deleting a device revokes it and its captures stay.

**Ownership:** `captures.user_id` is stored directly. Another user's resource returns 404, not 403. Keep that filter in any new query.

**Capture pipeline** (`services/capture_service.py`, `worker.py`, `recognition_service.py`, `image_service.py`, `log_service.py`):
- `ingest_capture` is shared by the device and phone routes. The `capture_id` (UUID from the device or app) makes retries idempotent: a retry by the same owner returns the stored capture with 200, anyone else gets 409, and a malformed or missing id is 422. This check runs before the image is read.
- The photo goes to local disk (`LOCAL_IMAGE_DIR`) before the database commit and is removed if the commit fails. The commit also queues two jobs (`recognize_capture`, `upload_image`). Only JPEGs are accepted (magic bytes). Phone photos have GPS EXIF removed without re-encoding; pixels are never touched.
- The worker claims jobs with `FOR UPDATE SKIP LOCKED`. The upload job copies the photo to Cloudinary then deletes the local file. The recognition job calls the AI, stores every run and candidate, and either logs automatically (confidence ≥ `VISION_AUTO_LOG_THRESHOLD` on a valid code) or sets `needs_review`.
- `log_service.try_log` is the single place that creates or updates a log entry. It locks the capture row because recognition and a weight update can arrive together. Nutrition is `amount_per_100g × weight_g ÷ 100` from the reference table only; nothing is estimated.
- Device weights are measured and locked; phone weights are user estimates and can be edited.
- Every committed change to a capture is pushed to the app with `presenters.publish_capture`; the device polls `GET /device/captures/{id}/status`.
- On delete the database row goes first (children cascade), then the local file and the Cloudinary image; a storage failure is only logged.
- Every state change records an `events` row in the same transaction via `event_service.record_event` (no commit inside). Never put tokens or keys in event data.

**Food data:** comes only from `Food_Composition_Table_Pakistan.xlsx`. Edit `data/reference/curation.csv` / `aliases.csv` by hand, never the extracted CSVs. `matchable_catalog()` is cached in memory, so restart the server after reseeding.

**Adding an integration:** define the interface beside the implementation, expose it through an `@lru_cache` getter in `dependencies.py`, and have routes receive it with `Depends`, so it can be replaced through `app.dependency_overrides`. Business code never imports a provider SDK (`openai` is imported only in `integrations/ai/openai_compatible_food_recognizer.py`). The worker calls the getters directly, so tests replace them on the `dependencies` module too.

## Constraints

Some Python names are part of the public API, so renaming them changes the API or its generated docs:

- route handler function names (OpenAPI `operationId`)
- Pydantic class names in `views/` (OpenAPI schema names)
- route parameter names such as `x_api_key` or `x_firmware_version` (header names) and form fields like `weight_g`
- route handler docstrings (endpoint descriptions)

Don't add return type annotations to route handlers: FastAPI would treat them as response models and change responses.

New models must be imported in `app/models/__init__.py`, because `migrations/env.py` relies on that to register tables for autogenerate.

Never edit an applied migration. `0001_baseline.py` is the only one; the two original migrations (and the removed `analyses` table) were deliberately discarded when the schema was rebuilt.

# Calop backend: implementation guide

This guide tells you, step by step, how to build the full Calop backend. Build real, working code: no placeholders, stubs or fake data. Work through the phases in order, because each one depends on the ones before it. After each phase, run its checks before starting the next.

All commands run from `calop-backend/`. Read `CLAUDE.md` first. Its general conventions still apply, but this guide replaces the specific rules listed in "Rules that change" below.

---

## What you are building

Calop is a food scale. An ESP32-S3 CAM weighs food and photographs it, AI identifies the food, and the server calculates nutrition from the real weight. Users can also log food with their phone camera, typing in an estimated weight. Users fill in a questionnaire once after signup, set a weight goal, and track their daily intake against a calculated target.

### The pipeline

```
Device or phone uploads photo (+ weight)
  → server saves the photo to local disk, the capture to the database, queues 2 jobs, replies 202
  → job A: AI recognition            job B: upload photo to Cloudinary (in parallel)
  → high confidence: log automatically
    lower confidence: user picks from the top 3 candidates or searches the table, or discards
  → nutrition = amount per 100 g × weight ÷ 100, using only the reference table
  → daily and weekly reports compare logged intake with the user's target
  → every status change is pushed to the app over a WebSocket; the device polls for status
```

### Fixed decisions (do not change these)

- **Prototype on a local network.** The server, device and phone share one Wi-Fi network. Gemini, Supabase (Postgres and Auth) and Cloudinary are still used over the internet.
- **Nutrition data comes only from `Food_Composition_Table_Pakistan.xlsx`.** No internet search, no AI-estimated nutrition, no second data source. Foods not in the table can't be logged; the team adds foods to the table over time.
- **Two capture sources:**
  - **Device:** sends whatever weight is on the scale, with no tare. The weight can never be edited.
  - **Phone:** the user types an estimated weight, which they can edit later.
- **Full-quality photos.** Never resize or re-encode images.
- **One device per user**, and one food item per capture. Multi-item plates come in a later phase.
- **Everything placed counts as eaten.** There's no leftovers handling, and all weight counts as edible.
- **The AI provider is switchable through config.** Business code never imports a provider SDK.
- **Recognition result:**
  - Confidence at or above the threshold, with a valid code: log automatically.
  - Otherwise: show the top 3 candidates plus a table search, with a Discard option.
- **Every automatic entry has "Wrong food?"**, which changes only the food.
- **Questionnaire:** shown once after signup, editable in settings, never asked again.
- **Goals are overall**, such as 85 kg to 65 kg in 8 months. The server calculates a daily target for calories, protein, fat and carbs.
  - Unrealistic goals get a warning and a suggested date, and the target never drops below a calorie floor.
  - Updating weight in settings recalculates the target.
- **Photos are deleted from local disk once Cloudinary confirms the upload.** The Cloudinary copy stays until the user deletes the capture.
- **All current data is dummy.** Reset the database and migrations.

### Out of scope (do not build)

The AI nutritionist assistant, deficiency insights and micronutrient targets, account export and deletion, push notifications, multi-item plates, cloud deployment, and the firmware and mobile app themselves. "Contracts for the firmware and the mobile app" at the end gives the contracts that the firmware and the app must follow.

---

## Rules that change

These replace the matching rules in `CLAUDE.md`. Update `CLAUDE.md` and `README.md` in the final phase.

| Old rule | New rule |
|---|---|
| Image goes to Cloudinary before the DB commit | Image goes to local disk before the DB commit. Cloudinary upload is a background job. |
| Captures belong to users through their device | `captures.user_id` is stored directly. Keep the "another user's resource returns 404" rule. |
| Malformed `capture_id` is replaced with a new UUID | A malformed or missing `capture_id` returns 422. |
| Form field `device_id` accepted and ignored | Removed. |
| Deleting a device with captures returns 409 | Deleting a device revokes it. Its captures stay. |
| Errors are `{"detail": message}` | Errors are `{"error": {"code", "message", "request_id"}}`. |
| Routes under `/api/...` | Routes under `/api/v1/...`. |
| No cascades | Deleting a capture cascades to its child rows (see Schema). |
| Never edit applied migrations | One-off exception: delete both old migrations and create a new baseline (phase 2). After that, the rule applies again. |

These rules stay:
- `controller → service → model / integration`.
- Services raise `ApplicationError` subclasses, never `HTTPException`.
- No return type annotations on route handlers.
- New models are imported in `app/models/__init__.py`.
- Integrations are exposed through `@lru_cache` getters in `controllers/dependencies.py`.

---

## Phase 1: Foundations

1. **Dependencies.**
   - Add to `requirements.txt`: `openai>=1.60` (the generic client for OpenAI-compatible APIs) and `piexif>=1.1.3`.
   - Create `requirements-dev.txt` with `-r requirements.txt`, `openpyxl>=3.1` and `pytest>=8`.
2. **Settings** (`app/core/config.py`). Add the following with defaults, and keep the existing settings:

   ```
   vision_ai_provider: str = "gemini"            # label stored on each recognition run
   vision_ai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
   vision_ai_api_key: str                        # required
   vision_ai_model: str                          # required, e.g. "gemini-3.8-flash"; check the model list in AI Studio
   vision_ai_reasoning_effort: str | None = "low"   # sent only if set; lowers latency
   vision_ai_timeout_seconds: float = 30
   vision_auto_log_threshold: float = 0.90
   local_image_dir: str = "storage/captures"
   max_device_image_bytes: int = 5 * 1024 * 1024
   max_phone_image_bytes: int = 12 * 1024 * 1024   # Gemini's inline request limit is 20 MB after base64
   worker_threads: int = 4
   ```

   Remove `max_image_bytes`. Add `storage/` to `calop-backend/.gitignore`.
3. **Errors** (`app/core/exceptions.py`).
   - Add a `code` argument to `ApplicationError`, with a default per subclass: `unauthorized`, `not_found`, `conflict`, `payload_too_large`, `unsupported_media_type`, `invalid_input`, `bad_gateway`.
   - Services pass specific codes, such as `ConflictError("...", code="device_exists")`.
4. **Request IDs and error handlers** (`app/main.py`).
   - Add middleware that creates a UUID per request, stores it in a `contextvars.ContextVar` (put it in `app/core/request_context.py`), and returns it in the `X-Request-ID` response header.
   - Exception handlers return `{"error": {"code", "message", "request_id"}}` for:
     - `ApplicationError`
     - `RequestValidationError`: code `invalid_input`, with the field errors under `error.fields`
     - unhandled exceptions: HTTP 500, code `internal_error`, logged with the traceback
5. **API prefix.** Every router uses a `/api/v1` prefix.
6. **Event helper** (`app/services/event_service.py`).
   - Add `record_event(db, actor_type, actor_id, action, entity_type, entity_id, data=None)`.
   - It adds an `Event` row to the session without committing, so the event commits in the same transaction as the change. It reads `request_id` from the context var.
   - Never put tokens, API keys or passwords in `data`.

**Check:** the server starts, and a bad request to any route returns the new error shape with a `request_id`.

---

## Phase 2: Database reset and models

1. **Drop the old tables first.** Run `alembic downgrade base`, while the old migration files still exist. This clears the app tables in the database that `DATABASE_URL` points to. Supabase Auth users are untouched.
2. Delete `app/migrations/versions/b39f3620898e_init.py` and `7c1e4a9d2f30_remove_analyses.py`.
3. Replace `app/models/` with the tables in the Schema section below: one module per area (`user.py`, `device.py`, `capture.py`, `food.py`, `log.py`, `job.py`, `event.py`), all imported in `app/models/__init__.py`.
4. Run `alembic revision --autogenerate -m "baseline"`, then edit the generated file:
   - Add `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")` as the first line of `upgrade()`. If Supabase rejects it, enable `pg_trgm` in the dashboard under Database → Extensions.
   - Check that partial unique indexes, check constraints and the GIN trigram index were generated. Add any that are missing by hand.
5. Run `alembic upgrade head`, then `alembic check`. The check must report no differences.

### Model conventions

- **Primary keys:** UUID, except where noted.
- **Timestamps:** `DateTime(timezone=True)`, server default `now()`.
- **Statuses:** `String` columns plus a `CheckConstraint` listing the allowed values. Don't use Postgres enums. Put the allowed values in a Python constant beside the model.
- **Quantities:** `Numeric`, which returns Python `Decimal`. Do the maths with `Decimal`, and convert to `float` only in views.

---

## Schema

Unless noted, columns are `NOT NULL`. `null` marks a nullable column.

### Users and goals

```
users
  id                       uuid PK        -- equals the Supabase user id; NOT a foreign key to Supabase
  email                    text null
  onboarding_completed_at  null
  created_at, updated_at

user_profiles
  user_id         PK FK users
  date_of_birth   date
  sex             'male' | 'female'
  height_cm       numeric(5,1)
  activity_level  'sedentary' | 'light' | 'moderate' | 'active' | 'very_active'
  diet_type       'none' | 'vegetarian'
  allergies       text[]  default '{}'
  timezone        text default 'Asia/Karachi'
  created_at, updated_at

weight_entries
  id, user_id FK users
  weight_kg     numeric(5,2)
  source        'onboarding' | 'settings'
  recorded_at
  INDEX (user_id, recorded_at desc)

goals
  id, user_id FK users
  start_weight_kg, target_weight_kg   numeric(5,2)
  start_date      date
  target_date     date
  status          'active' | 'replaced' | 'achieved'
  created_at, ended_at null
  UNIQUE (user_id) WHERE status = 'active'

nutrition_targets
  id, user_id FK users, goal_id FK goals null
  effective_from
  maintenance_kcal, daily_adjustment_kcal, energy_kcal   numeric(7,1)
  protein_g, fat_g, carbohydrate_g                       numeric(6,1)
  floor_applied   boolean
  method          text            -- 'mifflin_st_jeor_v1'
  inputs          jsonb           -- every input and factor used
  INDEX (user_id, effective_from desc)
```

### Devices

```
devices
  id, owner_id FK users
  name              text (1–100 chars)
  status            'active' | 'revoked'
  firmware_version  text null
  created_at, last_seen_at null, revoked_at null
  UNIQUE (owner_id) WHERE status = 'active'

device_api_keys
  id, device_id FK devices
  key_hash      char(64) UNIQUE       -- SHA-256 hex, from app/core/security.py
  key_prefix    text                  -- first 6 characters, for display
  created_at, last_used_at null, revoked_at null
  UNIQUE (device_id) WHERE revoked_at IS NULL
```

### Captures, recognition and jobs

```
captures
  id                uuid PK           -- generated by the device or the app
  user_id           FK users
  source            'device' | 'phone'
  device_id         FK devices null
  weight_g          numeric(7,1) null
  weight_source     'measured' | 'user_estimate'
  status            'identifying' | 'awaiting_weight' | 'needs_review' | 'logged' | 'discarded' | 'failed'
  selected_food_id  FK foods null     -- food chosen by AI or user, waiting for weight if needed
  not_in_catalog_label  text null     -- AI's name for a food outside the table
  image_status      'local' | 'uploaded' | 'upload_failed'
  image_local_path  text null
  image_url         text null
  image_public_id   text null
  image_bytes       int
  image_sha256      char(64)
  captured_at       null              -- client clock, if plausible (see phase 7)
  received_at, recognized_at null, resolved_at null, updated_at
  firmware_version  text null
  app_version       text null
  CHECK (source = 'device' AND device_id IS NOT NULL AND weight_source = 'measured' AND weight_g IS NOT NULL)
     OR (source = 'phone' AND device_id IS NULL AND weight_source = 'user_estimate')
  CHECK weight_g IS NULL OR weight_g > 0
  INDEX (user_id, received_at desc)
  INDEX (user_id, status) WHERE status IN ('identifying', 'awaiting_weight', 'needs_review')

recognition_runs                      -- ON DELETE CASCADE from captures
  id, capture_id FK
  attempt           smallint
  provider, model, prompt_version     text
  status            'running' | 'succeeded' | 'failed' | 'rate_limited'
  decision          'auto_logged' | 'needs_review' | null
  top_confidence    numeric(4,3) null
  latency_ms, input_tokens, output_tokens   int null
  error_code, error_message           text null
  raw_response      jsonb null
  started_at, finished_at null

recognition_candidates                -- ON DELETE CASCADE from recognition_runs
  run_id FK, rank smallint            PK (run_id, rank)
  returned_code     text
  food_id           FK foods null     -- null when the returned code is not a matchable food
  confidence        numeric(4,3)

jobs                                  -- ON DELETE CASCADE from captures
  id                bigint identity PK
  kind              'recognize_capture' | 'upload_image'
  capture_id        FK
  status            'queued' | 'running' | 'succeeded' | 'failed'
  attempts          smallint default 0
  max_attempts      smallint
  run_after, locked_at null, last_error text null, created_at, updated_at
  INDEX (status, run_after)
```

### Food log

```
food_log_entries                      -- ON DELETE CASCADE from captures
  id, user_id FK users
  capture_id      FK captures UNIQUE  -- drop UNIQUE in the multi-item phase
  food_id         FK foods
  weight_g        numeric(7,1)
  weight_source   'measured' | 'user_estimate'
  resolution      'auto' | 'user_selected' | 'user_corrected'
  eaten_at
  local_date      date
  created_at, updated_at
  INDEX (user_id, local_date)

food_log_entry_nutrients              -- ON DELETE CASCADE from food_log_entries
  entry_id FK, nutrient_id FK         PK (entry_id, nutrient_id)
  amount          numeric(10,3)
```

### Reference data

```
food_sources    id smallint PK, code UNIQUE, title, publisher, year smallint, url null
food_groups     id smallint PK, code UNIQUE, name, sort_order smallint
nutrients       id smallint PK, code UNIQUE, name, unit, sort_order smallint, is_reported boolean

foods
  id                  int identity PK
  code                text UNIQUE     -- 'MAIN-19', 'TRAD-13', 'WEAN-1'
  source_id FK, source_ref text       -- the book's Sr. No.
  group_id FK
  source_name         text            -- as printed
  source_local_name   text null       -- the sheet's "Urdu" column (Roman Urdu)
  display_name        text
  scientific_name     text null
  kind                'ingredient' | 'dish' | 'recipe'
  preparation_state   'raw' | 'cooked' | 'processed' | 'unknown'
  is_matchable        boolean         -- may the AI choose it?
  is_searchable       boolean         -- may users and search find it?
  quality_flags       text[] default '{}'
  ingredients_text, preparation_method   text null
  created_at, updated_at

food_nutrients
  food_id FK, nutrient_id FK          PK (food_id, nutrient_id)
  amount_per_100g     numeric(10,3)   -- no row = not reported in the source

food_aliases
  id, food_id FK
  alias               text
  normalized_alias    text
  kind                'source' | 'local' | 'common' | 'spelling'
  is_preferred        boolean
  UNIQUE (food_id, normalized_alias)
  UNIQUE (normalized_alias) WHERE is_preferred
  GIN INDEX (normalized_alias gin_trgm_ops)

food_search_misses
  id, user_id FK null, query text, normalized_query text, context 'app_search', created_at
```

### History

```
events
  id            bigint identity PK
  occurred_at
  actor_type    'user' | 'device' | 'system' | 'ai'
  actor_id      uuid null
  action        text
  entity_type   text
  entity_id     text
  request_id    uuid null
  data          jsonb null
  INDEX (entity_type, entity_id), INDEX (actor_id, occurred_at)
```

---

## Phase 3: Reference data

The workbook sits at the repo root. Move it to `calop-backend/data/reference/source/Food_Composition_Table_Pakistan.xlsx` and commit it.

### 3.1 Extract (script: `scripts/extract_reference_data.py`)

This script reads the workbook with `openpyxl` (`data_only=True`) and writes CSV files to `data/reference/extracted/`. It never changes values. The extracted files are generated, so nobody edits them by hand.

**Workbook layout:**
- There are 15 sheets.
- Row 1 of each sheet is the header.
- Skip any row whose first cell isn't an integer: this covers section notes, footnotes and blank rows.
- Fail with a clear error on any header not listed below.

| Sheet | Group code | Food code | Kind |
|---|---|---|---|
| Cereal | `cereal` | `MAIN-<Sr. No.>` | ingredient |
| Legumes | `legumes` | `MAIN-…` | ingredient |
| Vegetables | `vegetables` | `MAIN-…` | ingredient |
| Roots and Tubers | `roots_tubers` | `MAIN-…` | ingredient |
| Spices | `spices` | `MAIN-…` | ingredient |
| Fruits | `fruits` | `MAIN-…` | ingredient |
| Nuts and Dry Fruits | `nuts_dry_fruits` | `MAIN-…` | ingredient |
| Dairy | `dairy` | `MAIN-…` | ingredient |
| Meat | `meat` | `MAIN-…` | ingredient |
| Fish | `fish` | `MAIN-…` | ingredient |
| Eggs | `eggs` | `MAIN-…` | ingredient |
| Fats and Oil | `fats_oils` | `MAIN-…` | ingredient |
| Sugars and Beverages | `sugars_beverages` | `MAIN-…` | ingredient |
| Traditional Foods | `traditional_dishes` | `TRAD-<Sr. No.>` | dish |
| Weaning Foods | `weaning_foods` | `WEAN-<No.>` | recipe |

**Non-nutrient headers:**

| Header | Field |
|---|---|
| `Sr. No.`, `No.` | source_ref |
| `Food (English)`, `Dish`, `Food / Recipe` | source_name |
| `Food (Urdu)` | source_local_name |
| `Scientific Name` | scientific_name |
| `Ingredients and Amounts` | ingredients_text |
| `Method of Preparation` | preparation_method |
| `Type` | ignore (all weaning rows are recipes anyway) |
| `Appendix Ref.` | ignore |
| `Reference Weight (gm)` | must equal 100 on every row, or fail |

**Nutrient headers.** The `nutrients` table seed comes from this list (sort order as listed):

| Header(s) | code | unit | is_reported |
|---|---|---|---|
| `Food Energy (kcal)`, `Energy (kcal)` | `energy_kcal` | kcal | true |
| `Protein (g)` | `protein_g` | g | true |
| `Lipid / Fat (g)`, `Fat (g)`, `Fat / Oil (g)` | `fat_g` | g | true |
| `Carbohydrate (g)`, `Carbohydrates (g)` | `carbohydrate_g` | g | true |
| `Fibre (g)` | `fibre_g` | g | true |
| `Calcium (mg)` | `calcium_mg` | mg | true |
| `Phosphorus (mg)` | `phosphorus_mg` | mg | true |
| `Iron (mg)` | `iron_mg` | mg | true |
| `Zinc (mg)` | `zinc_mg` | mg | true |
| `Thiamin (mg)` | `thiamin_mg` | mg | true |
| `Riboflavin (mg)` | `riboflavin_mg` | mg | true |
| `Niacin (mg)` | `niacin_mg` | mg | true |
| `Vitamin C (mg)` | `vitamin_c_mg` | mg | true |
| `β-Carotene (mcg)` | `beta_carotene_ug` | µg | true |
| `Vitamin A (RE)` | `vitamin_a_re` | RE | true |
| `Cholesterol (mg)` | `cholesterol_mg` | mg | true |
| `Moisture (g)` | `moisture_g` | g | false |
| `Ash (g)` | `ash_g` | g | false |
| `Iodine (ppm)` | `iodine_ppm` | ppm | false (units look wrong in the source; never report it) |

**Values:**
- An empty cell or `-` means not reported, so write no row.
- A number is written as `Decimal(str(value))` rounded to 3 decimal places, so `72.599999999999994` becomes `72.6`.
- Anything else fails the script.
- Trim whitespace in text fields. Empty text becomes null.

**Outputs:**
- `foods.csv`: code, source_ref, group_code, kind, source_name, source_local_name, scientific_name, ingredients_text, preparation_method
- `food_nutrients.csv`: food_code, nutrient_code, amount_per_100g
- `food_groups.csv`: code, name (from the sheet name), sort_order (sheet order)

**Expected counts.** The script fails if any of these don't match:
- 224 foods: 198 `MAIN` (codes 1–198, no gaps), 17 `TRAD` and 9 `WEAN`
- 15 groups
- 19 nutrients

### 3.2 Curate (hand-maintained: `data/reference/curation.csv` and `data/reference/aliases.csv`)

`curation.csv` has one row per food: `code, display_name, preparation_state, is_matchable, is_searchable`. Create it once by applying the rules below, then commit it. After that, people edit it by hand.

**`display_name`:** use `source_name`, except for these:

| Code | Display name | Code | Display name |
|---|---|---|---|
| MAIN-18 | Naan | MAIN-75 | Cardamom |
| MAIN-19 | Chapati | MAIN-90 | Grapes |
| MAIN-20 | Paratha | MAIN-91 | Grapes (second sample) |
| MAIN-21 | Puri | MAIN-103 | Kinnow |
| MAIN-22 | Double Roti (Bread) | MAIN-104 | Mandarin (Narangi) |
| MAIN-23 | Biscuit | MAIN-115 | Ber (Desi) |
| MAIN-44 | Sponge Gourd (Tori) | MAIN-116 | Ber (Sova) |
| MAIN-47 | Brinjal (Baingan) | MAIN-120 | Betel Nut |
| MAIN-72 | Radish | MAIN-125 | Poppy Seed |
| MAIN-196 | Instant Coffee (Dry Powder) | WEAN-6…9 | Supplementary Food Mix 1…4 |

**`preparation_state`:**
- **cooked:** MAIN 9, 10, 25, 27, 29, 31, 33, 35, 37, 39, 41, 123, 167, 171, and all TRAD.
- **raw:** MAIN 24, 26, 28, 30, 32, 34, 36, 38, 40, 164, 165, 166, 168, 169, 170, 175, and fruits 83–116 except 87.
- **processed:** MAIN 1–7, 11–23, 87, 128–132, 137–140, 172–174, 176–198, and all WEAN.
- **unknown:** everything else.

**`is_matchable = false`:**
- Spices (74–82) and fats and oils (172–184).
- Flours and raw grain: 1, 2, 5, 6, 7, 8, 12, 15, 16, 17.
- Raw pulses: 24, 26, 28, 30, 32, 34, 36, 38, 40.
- Raw eggs: 164, 165, 166, 168, 169, 170.
- Human milk 136, and milk powders 137 and 138.
- Coffee and tea 196–198.
- Duplicates: MAIN-91 and TRAD-1. MAIN-19 has more nutrients and is the Chapati to match.
- All WEAN foods.
- Everything else is `true`.

**`is_searchable = false`:** MAIN-136, TRAD-1 and all WEAN foods. Everything else is `true`.

**`quality_flags`:** this is computed during seeding, not stored in the CSV. Add `energy_mismatch` when protein, fat, carbs and energy all exist and `|4·protein + 9·fat + 4·carbs − energy| / energy > 0.20`. Values are imported exactly as written either way (expect about 19 MAIN foods, including MAIN-131 cheese).

**`aliases.csv`** (`food_code, alias, kind, is_preferred`). The seed also generates aliases automatically from `source_name` (kind `source`), `source_local_name` (kind `local`) and `display_name` (kind `common`):
- An automatic alias is preferred only if its normalized form belongs to exactly one searchable food.
- Hand-written aliases in `aliases.csv` override that.

Start `aliases.csv` with this list, then extend it:

```
MAIN-19: roti, chapati, chapatti, phulka            (preferred)
MAIN-18: naan, nan
MAIN-20: paratha, parata, parotha
MAIN-21: puri, poori
MAIN-22: double roti, bread, white bread
MAIN-9:  chawal, chaval, rice, boiled rice, plain rice
MAIN-10: fried rice
MAIN-27: chana, chole, cooked chickpeas
MAIN-129: lassi, buttermilk         MAIN-130: dahi, curd       MAIN-139: yogurt
MAIN-131: paneer, cheese            MAIN-167: anda, boiled egg
MAIN-71: aloo, potato   MAIN-70: pyaz, onion   MAIN-63: tamatar, tomato
MAIN-83: seb, apple     MAIN-85: kela, banana   MAIN-99: aam, mango   MAIN-101: tarbooz, watermelon
MAIN-189: barfi         MAIN-190: jalebi, jalebe
TRAD-2:  daal, dal, masoor daal, dal masoor
TRAD-3:  aloo gosht, alu gosht, aloo ghosht
TRAD-4:  rajma, kidney bean curry
TRAD-5:  kofta, kofte
TRAD-6:  pulao, pulav, beef pulao, yakhni pulao
TRAD-7:  shami kabab, shami kebab
TRAD-8:  chapli kabab, chapli kebab, chapal kabab
TRAD-9:  chicken curry, chicken salan
TRAD-10: haleem, daleem
TRAD-11: fried fish, machli, machli fry
TRAD-12: sajji
TRAD-13: biryani, biriyani, chicken biryani
TRAD-14: suji halwa, sooji halwa
TRAD-15: zarda, meethe chawal
TRAD-16: kheer
TRAD-17: gajar halwa, gajar ka halwa
```

Mark every alias in this list `is_preferred = true`, with kind `common` or `spelling`.

**Normalization** (`app/services/food_text.py`, used by both the seed and search):
1. Apply NFKD and drop accents.
2. Lowercase.
3. Replace every character that isn't a letter or digit with a space.
4. Collapse repeated spaces and trim.

### 3.3 Seed (`python -m app.seeds.reference`)

1. Load `extracted/*.csv`, `curation.csv` and `aliases.csv`.
2. Validate everything before writing. Fail with a full list of problems if any of these occur:
   - a food code is missing from `curation.csv`, or listed there but unknown
   - an alias points to an unknown food
   - more than one preferred alias shares a normalized form
   - a nutrient value is negative
   - protein + fat + carbs + fibre exceeds 105 g
   - an enum value is invalid
3. In one transaction, upsert:
   - `food_sources`: one row, code `fct_pk_2001`, title "Food Composition Table for Pakistan (Revised 2001)", publisher "Dept. of Agricultural Chemistry, NWFP Agricultural University Peshawar; UNICEF; Ministry of Planning & Development", year 2001, url `https://www.fao.org/infoods/infoods/tables-and-databases/pakistan/en/`
   - `food_groups`, keyed by code
   - `nutrients`, keyed by code
   - `foods`, keyed by code
   - `food_nutrients`: delete and reinsert each food's rows
   - `food_aliases`: delete and reinsert for each food
4. Print the counts.

Running it twice must give the same result. Don't seed from a migration.

**Check:** the seed prints 224 foods, 15 groups and 19 nutrients. Also check these lookups:
- `MAIN-19` has 19 nutrient rows, minus any that were blank.
- `TRAD-13` has no `zinc_mg` row.
- Normalized `roti` has exactly one preferred alias, pointing to `MAIN-19`.

---

## Phase 4: Food search and nutrition

### Services (`app/services/food_service.py`)

- **`search_foods(db, query, group_code=None, limit=10)`**
  1. Normalize the query.
  2. Look for exact matches on `normalized_alias` among searchable foods.
     - If any are found, return them with `match_type = "exact"`, the preferred alias first.
  3. Otherwise, run a trigram search: `similarity(normalized_alias, :q) > 0.3`, ordered by similarity, one row per food (its best alias score).
     - Return these with `match_type = "fuzzy"`.
  4. If nothing matches, return `match_type = "none"` with an empty list, and insert a `food_search_misses` row.
- **`get_food(db, code)`**: the food with group, aliases and all nutrients. Unknown code: `NotFoundError(code="food_not_found")`.
- **`compute_nutrition(food, weight_g)`**: a pure function.
  - For every nutrient row, `amount = amount_per_100g × weight_g / 100`, rounded to 3 decimal places.
  - Returns the amounts, plus the codes of reported nutrients the food lacks (`missing`).
  - Never invent or estimate values.
- **`matchable_catalog()`**: the matchable foods as `(code, display_name, preparation_state, up to 5 aliases)`, cached in memory. Restart the server after reseeding.

### Routes (`controllers/food_controller.py`, Bearer auth)

| Route | Response |
|---|---|
| `GET /api/v1/foods?q=&group=&limit=` | `{match_type, items: [{code, display_name, group, preparation_state, score}]}`. Require `q` or `group`. |
| `GET /api/v1/foods/{code}` | Food detail: aliases, `quality_flags`, nutrients `[{code, name, unit, amount_per_100g}]` |
| `GET /api/v1/foods/{code}/nutrition?weight_g=` | `{food, weight_g, nutrients: [{code, name, unit, amount}], missing: [codes]}` |
| `GET /api/v1/food-groups` | `[{code, name}]` |

**Check:**
- `q=roti` gives an exact match to `MAIN-19`.
- `q=biriyani` matches `TRAD-13`.
- `q=chappati` gives a fuzzy match to `MAIN-19`.
- `MAIN-19/nutrition?weight_g=50` returns half of each per-100 g value.

---

## Phase 5: Users, questionnaire and targets

### Target calculator (`app/services/target_calculator.py`)

Write this as pure functions with no database access, and unit test them.

**Inputs:** sex, age in whole years, height_cm, current weight_kg, activity_level, target_weight_kg, target_date and today.

**Calculation:**
1. BMR: `10·kg + 6.25·cm − 5·age + 5` for males, or `… − 161` for females.
2. Maintenance: BMR × activity factor:

   | Activity level | Factor |
   |---|---|
   | sedentary | 1.2 |
   | light | 1.375 |
   | moderate | 1.55 |
   | active | 1.725 |
   | very_active | 1.9 |
3. `change_kg = target − current`. The goal type is `maintain` if `|change_kg| < 0.5`, otherwise `lose` or `gain`.
4. `days = (target_date − today).days`. It must be greater than 0, unless the goal type is maintain.
5. `adjustment = change_kg × 7700 / days`, clamped to ±1100 kcal (1 kg per week). If it was clamped, add a warning `goal_too_fast` with `suggested_target_date = today + ceil(|change_kg| × 7)` days.
6. `energy = maintenance + adjustment`. The floor is 1200 kcal for females and 1500 kcal for males. If energy is below the floor:
   - set energy to the floor and `floor_applied = true`
   - add a warning `calorie_floor` with `suggested_target_date = today + ceil(|change_kg| × 7700 / (maintenance − floor))` days
   - if `maintenance ≤ floor`, return no suggested date
7. Split the energy into protein, fat and carbs, using 4, 9 and 4 kcal per gram:

   | Goal | Protein | Fat | Carbs |
   |---|---|---|---|
   | lose | 30% | 30% | 40% |
   | maintain | 20% | 30% | 50% |
   | gain | 25% | 25% | 50% |
8. Return the targets, the warnings and an `inputs` dict containing every value used.

### Service (`app/services/profile_service.py`)

- **`complete_onboarding(db, user, body)`**
  - Fails with 409 `onboarding_already_completed` if done before.
  - Age must be at least 18, or 422 `under_18`: Gemini's terms require users to be 18 or over.
  - Height must be 100–250 cm and weight 25–350 kg.
  - Creates in one transaction: the profile, a weight entry (source `onboarding`), the active goal (start weight = current weight, start date = today) and a target row. It also sets `onboarding_completed_at` and records events.
- **`recalculate_target(db, user)`**: inserts a new `nutrition_targets` row with `effective_from = now()`, using the latest weight. Call it after a profile change, a new weight or a goal change.
- **Goal achieved:** when a new weight reaches the goal (at or below target for lose, at or above for gain):
  - mark the goal `achieved` with `ended_at = now()`
  - calculate maintain targets with `goal_id = null`

### Routes (Bearer auth)

| Route | Behaviour |
|---|---|
| `GET /api/v1/me` | `{id, email, onboarding_completed, profile, current_weight_kg, goal, target}` |
| `POST /api/v1/me/onboarding` | Body: `date_of_birth, sex, height_cm, weight_kg, activity_level, diet_type, allergies, target_weight_kg, target_date`. Returns `{profile, goal, target, warnings}`. |
| `PATCH /api/v1/me/profile` | Any profile field. Recalculates the target. |
| `POST /api/v1/me/weights` | Body `{weight_kg}`. Recalculates the target, and may mark the goal achieved. |
| `GET /api/v1/me/weights?from=&to=` | List of weight entries. |
| `PUT /api/v1/me/goal` | Body `{target_weight_kg, target_date}`. Marks the old goal `replaced` and creates a new active one. Returns `{goal, target, warnings}`. |
| `GET /api/v1/me/activity?limit=&offset=` | The user's events, newest first. |

Remove the old `GET /api/auth/me`. Keep signup, login and refresh unchanged, under `/api/v1/auth/`.

Warnings never block the request. The app shows the suggested date, and the user can resubmit with it.

**Check:**
- Unit tests cover the 85 → 65 kg in 8 months example, a too-fast goal, the calorie floor, maintain, and gain.
- `POST /me/onboarding` twice gives a 409 the second time.

---

## Phase 6: Devices

### Services (`app/services/device_service.py`)

- **`create_device(db, user, name)`**: fails with 409 `device_exists` if the user already has an active device. Otherwise it generates a key with `generate_api_key()`, stores its hash and the first 6 characters, and returns the plain key once.
- **`authenticate_device(db, api_key)`**
  - Finds the key row by hash, where `revoked_at` is null and the device is active.
  - If none is found: `AuthError("Invalid API key", code="invalid_api_key")`.
  - Updates `last_used_at`, `devices.last_seen_at` and `firmware_version` (from the `X-Firmware-Version` header, if sent).
- **`rotate_key`**: revokes the active key and creates a new one, returning it once.
- **`revoke_device`**: sets the device to revoked, revokes its keys and sets `revoked_at`. Captures stay.

### Routes (Bearer auth)

| Route | Behaviour |
|---|---|
| `POST /api/v1/devices` | `{name}` → 201 `{id, name, status, created_at, last_seen_at, api_key}` |
| `GET /api/v1/devices` | List of the user's devices, active and revoked |
| `GET /api/v1/devices/{id}` | One device |
| `PATCH /api/v1/devices/{id}` | `{name}` |
| `POST /api/v1/devices/{id}/rotate-key` | → `{api_key}` |
| `DELETE /api/v1/devices/{id}` | Revokes the device → 204 |

The `X-API-Key` dependency stays in `dependencies.py`, with the parameter name `x_api_key`.

**Check:**
- Creating a second device returns 409.
- After rotating, the old key returns 401 and the new key works.

---

## Phase 7: Capture ingest

### Service (`app/services/capture_service.py`): `ingest_capture(...)`, shared by device and phone uploads

1. **Check the ID.** `capture_id` must parse as a UUID, or return 422 `invalid_capture_id`.
2. **Handle retries first, before reading the image.** If a capture with this ID exists:
   - Same owner, and for device uploads the same device: return it with HTTP 200.
   - Anything else: 409 `capture_id_in_use`.
3. **Read and check the image.** Read up to `max_*_image_bytes + 1` bytes.
   - Over the limit: 413.
   - First 3 bytes not `FF D8 FF`: 415 `jpeg_required`.
4. **Phone only: remove GPS metadata without touching pixels.** Use `piexif.load`. If the data has a `GPS` IFD, empty it, then `piexif.insert(piexif.dump(exif), data, out)` into a `BytesIO`. If piexif raises, keep the original bytes and log a warning. Never re-encode the image.
5. **Save the file.** Compute the SHA-256 and write the bytes to `{local_image_dir}/{capture_id}.jpg`, writing a temp file first and then using `os.replace`.
6. **Check the weight.** It must be greater than 0 and at most 50000, or return 422 `invalid_weight`. Device uploads require a weight; phone uploads may leave it out.
7. **Check `captured_at`.** Keep it only if it's no more than 5 minutes in the future and no more than 7 days in the past. Otherwise store null.
8. **Insert in one transaction:**
   - the capture, with status `identifying` and image_status `local`
   - two jobs: `recognize_capture` (max_attempts 6) and `upload_image` (max_attempts 10), both `run_after = now()`
   - a `capture.received` event
9. **If the commit fails,** delete the local file and re-raise.
10. **After the commit,** wake the worker (phase 8), publish `capture.updated` (phase 10), and return the capture with HTTP 202.

### Routes

| Route | Auth | Form fields | Response |
|---|---|---|---|
| `POST /api/v1/device/captures` | `X-API-Key` | `capture_id`, `weight_g`, `image`, optional `captured_at` (ISO 8601) | 202 new / 200 retry |
| `POST /api/v1/captures` | Bearer | `capture_id`, `image`, optional `weight_g` and `captured_at` | 202 new / 200 retry |

The phone route reads the `X-App-Version` header into `app_version`.

To return 202 or 200 from the same handler, set `response.status_code` through an injected `Response` parameter. Don't add a return annotation.

**Check:**
- An upload creates a file under `storage/captures/` and two queued jobs.
- Sending the same upload again returns 200 with the same capture.
- A PNG returns 415.

---

## Phase 8: Worker, Cloudinary upload and AI recognition

### Job queue (`app/services/job_service.py`)

- **`claim_next(db)`**:
  1. `SELECT … FROM jobs WHERE status='queued' AND run_after <= now() ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED` (in SQLAlchemy, `with_for_update(skip_locked=True)`).
  2. Set the job to running, set `locked_at`, increment `attempts`, and commit.
- **`retry_later(db, job, delay_s, error)`**: if attempts remain, set the job back to queued with `run_after = now() + delay`. Otherwise set it to `failed`.
- **On startup:** reset jobs that have been `running` for more than 5 minutes back to `queued`. This handles crash recovery.

### Worker (`app/worker.py`)

- Start it from the FastAPI `lifespan`, and stop it on shutdown.
- It uses a `ThreadPoolExecutor(worker_threads)`.
- Each thread loops: claim a job and run it. If none is available, wait on a shared `threading.Event` for up to 1 second.
- `wake()` sets the event, so new jobs start immediately.
- Each job uses its own `SessionLocal()`, and the session must be closed afterwards.
- Run the server as **one process** (no `--workers`), because the worker and the WebSocket hub live in memory:

  ```
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```

### Upload job (`upload_image`)

1. Load the capture. If it no longer exists, delete the local file if present, and mark the job succeeded.
2. Read the local file and call `ImageStorage.upload(bytes)`. The existing Cloudinary implementation already does this.
3. **On success:**
   - set `image_url`, `image_public_id`, `image_status = 'uploaded'` and `image_local_path = null`
   - commit, then delete the local file
   - record `capture.image_uploaded` and publish `capture.updated`
4. **On `StorageError`:** retry with delays of 5, 15, 30, 60 and 120 seconds, capped at 300 seconds. After the last attempt, set `image_status = 'upload_failed'`, keep the local file, and record an event.

### AI layer (loose coupling)

**Interface:** `app/integrations/ai/food_recognizer.py`.

```python
@dataclass
class RecognizedCandidate:
    code: str
    confidence: float

@dataclass
class RecognitionOutput:
    candidates: list[RecognizedCandidate]
    not_in_catalog_label: str | None
    raw_response: dict
    input_tokens: int | None
    output_tokens: int | None

class RecognizerRateLimited(Exception): ...
class RecognizerError(Exception): ...

class FoodRecognizer(ABC):
    @abstractmethod
    def recognize(self, image_jpeg: bytes, catalog_text: str) -> RecognitionOutput: ...
```

**Implementation:** `app/integrations/ai/openai_compatible_food_recognizer.py`. It's the only file that imports `openai`.
- Create `OpenAI(base_url=settings.vision_ai_base_url, api_key=settings.vision_ai_api_key, timeout=settings.vision_ai_timeout_seconds, max_retries=0)`. Retries are handled by the job queue.
- Build a chat request:
  - the system prompt
  - one user message with the catalog text and the image, as `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<b64>"}}`
- Request structured output with the SDK's parse helper and a Pydantic model:

  ```python
  class _Candidate(BaseModel):
      code: str
      confidence: float = Field(ge=0, le=1)

  class _Result(BaseModel):
      candidates: list[_Candidate] = Field(max_length=3)
      not_in_catalog_label: str | None
  ```

  Use `client.chat.completions.parse(...)`; on older SDKs it's `client.beta.chat.completions.parse(...)`. Pass `reasoning_effort` only when the setting is set.
- **Errors:**
  - `openai.RateLimitError`: raise `RecognizerRateLimited`.
  - Other `openai.APIError`, timeouts, or output that fails validation: raise `RecognizerError`.
- Fill `raw_response` from `completion.model_dump()`.

**Getter:** add an `@lru_cache` `get_food_recognizer()` in `dependencies.py`. Switching providers then means changing the `VISION_AI_*` settings. A provider without an OpenAI-compatible API needs one new class implementing `FoodRecognizer`.

**Prompt** (`prompt_version = "recognize-v1"`), stored as a constant in `recognition_service.py`:

```
You identify the single food item in a photo for a nutrition app in Pakistan.
Choose ONLY from the catalog below. Each line is: CODE | name | preparation state | other names.
Return up to 3 candidates, most likely first, with confidence between 0 and 1.
Confidence must reflect real uncertainty; do not give high confidence unless you are sure.
If the food is not in the catalog, return no candidates and put your best name for it in
not_in_catalog_label. Otherwise set not_in_catalog_label to null.
```

The catalog text is one line per matchable food, such as `MAIN-19 | Chapati | processed | roti, chapatti, phulka`.

### Recognition job (`recognize_capture`, in `app/services/recognition_service.py`)

1. Load the capture. If it's gone, or its status is no longer `identifying`, mark the job succeeded and stop.
2. Read the image from the local file, or download it from `image_url` if it has already been uploaded.
3. Insert a `recognition_runs` row with status `running`, provider, model, prompt_version and attempt, then call `recognize`. Measure `latency_ms`.
4. **On `RecognizerRateLimited`:** mark the run `rate_limited` and retry the job after 2, 5, 15, 30 or 60 seconds.
   **On `RecognizerError`:** mark the run `failed` and retry the same way.
   **When attempts run out:** set the capture to `failed`, then record the event and publish.
5. **On success:**
   - Save candidates: map each returned code to a matchable food. Candidates with unknown codes are stored with `food_id = null`.
   - Set `top_confidence` from the first valid candidate.
   - **Decide:**
     - First valid candidate with confidence ≥ `vision_auto_log_threshold`: `decision = 'auto_logged'`, `selected_food_id = that food`, then call `try_log(capture, resolution='auto')` (phase 9).
     - Otherwise: `decision = 'needs_review'` and capture status `needs_review`.
   - Store `not_in_catalog_label`, set `recognized_at`, and record `capture.recognized`.
6. Commit, then publish `capture.updated`.

**Check:**
- With a real `VISION_AI_API_KEY`, photograph a roti on the device or with `curl`. The capture should reach `logged` or `needs_review` within a few seconds, and `recognition_runs` should hold the raw response.
- Set the model to a nonexistent ID and confirm the capture ends `failed` after its retries.

---

## Phase 9: Resolving and logging

### `try_log(db, capture, resolution)` in `app/services/log_service.py`

Lock the capture row with `SELECT … FOR UPDATE`, because recognition and a weight update can arrive at the same time. Then:

1. **No `selected_food_id`:** do nothing.
2. **No `weight_g`:** set status `awaiting_weight`, which only happens for phone captures.
3. **Otherwise, create or update the log entry:**
   - Set `weight_g` and `weight_source` from the capture, `food_id = selected_food_id`, and the given resolution.
   - `eaten_at = captured_at or received_at`.
   - `local_date = eaten_at` converted to the profile timezone, using `zoneinfo`. Without a profile, use `Asia/Karachi`.
   - Replace its `food_log_entry_nutrients` with `compute_nutrition(food, weight_g)`.
   - Set the capture to `logged` with `resolved_at = now()`.
   - Record `entry.created` or `entry.recalculated`.

### Routes (Bearer auth; another user's capture returns 404)

| Route | Allowed when | Behaviour |
|---|---|---|
| `GET /api/v1/captures?status=&source=&from=&to=&limit=&offset=` | any | Newest first: `{items, total, limit, offset}` |
| `GET /api/v1/captures/{id}` | any | Full capture (shape below) |
| `GET /api/v1/captures/{id}/image` | any | If uploaded: 307 redirect to `image_url`. Otherwise `FileResponse` from the local file. |
| `PATCH /api/v1/captures/{id}` | phone captures, any status except discarded | `{weight_g}` → updates the weight, then `try_log` (keeps the resolution) and records `capture.weight_changed`. Device captures: 409 `weight_locked`. |
| `POST /api/v1/captures/{id}/select` | `needs_review`, `awaiting_weight` | `{food_code}` must be a searchable food → `selected_food_id`, then `try_log(resolution='user_selected')` |
| `POST /api/v1/captures/{id}/discard` | `needs_review`, `awaiting_weight`, `failed` | Status `discarded`. Kept on record but never counted. |
| `POST /api/v1/captures/{id}/reprocess` | `failed`, `needs_review` | Status `identifying`, plus a new `recognize_capture` job |
| `DELETE /api/v1/captures/{id}` | any | Deletes the row (cascades to its children) and commits. Then deletes the local file, and the Cloudinary image if uploaded; a `StorageError` here is only logged. Records `capture.deleted` and publishes `capture.deleted`. Returns 204. |
| `GET /api/v1/log-entries?from=&to=` | any | Entries by `local_date` range, with food and nutrients |
| `GET /api/v1/log-entries/{id}` | any | One entry |
| `PATCH /api/v1/log-entries/{id}` | any | `{food_code}`, the "Wrong food?" action: sets the capture's `selected_food_id` and recalculates with `resolution='user_corrected'` |

**Capture response shape:**

```json
{
  "id": "…", "source": "device", "status": "needs_review",
  "weight_g": 182.0, "weight_source": "measured",
  "image_status": "uploaded", "image_url": "/api/v1/captures/…/image",
  "captured_at": "…", "received_at": "…",
  "candidates": [{"code": "MAIN-19", "display_name": "Chapati", "confidence": 0.71}],
  "not_in_catalog_label": null,
  "selected_food": null,
  "entry": null
}
```

- `image_url` is always the API image route, so the app doesn't need to know where the file lives.
- `candidates` come from the latest run and include only valid foods.
- `entry` is `{id, food: {code, display_name}, weight_g, weight_source, resolution, local_date, nutrients: [{code, name, unit, amount}], missing: [codes]}`.

**Check:**
- Run a phone capture without a weight, then send `PATCH` with a weight. It reaches `logged` with correct nutrients.
- `PATCH` on a device capture returns 409.
- "Wrong food?" changes the nutrients.

---

## Phase 10: Live updates and device status

### WebSocket hub (`app/realtime.py`)

- In memory, map `user_id → set[WebSocket]`.
- Save the running event loop at startup.
- `publish(user_id, message)` is thread-safe: it uses `asyncio.run_coroutine_threadsafe(send_all(...), loop)`, so request threads and worker threads can call it.
- Drop sockets that fail to send.

### Route `WS /api/v1/ws`

1. Accept the connection.
2. The first message must be `{"type": "auth", "token": "<access token>"}` and arrive within 5 seconds. Otherwise close with code 4401.
3. Verify the token with `AuthProvider.verify_token`, register the socket and send `{"type": "ready"}`.
4. Ignore other incoming messages, except `{"type": "ping"}`, which gets `{"type": "pong"}`.

**Messages to the app:**
- `{"type": "capture.updated", "capture": <capture shape>}`: sent after every commit that changes a capture, its image status or its entry
- `{"type": "capture.deleted", "id": "…"}`

When the app reconnects or opens, it calls `GET /captures?status=needs_review` and `GET /captures?status=awaiting_weight`, so it never depends on messages it missed.

### Device status (`X-API-Key`)

`GET /api/v1/device/captures/{id}/status` returns `{"status": …}`, mapped from the capture status:

| Capture status | Response |
|---|---|
| `identifying` | `processing` |
| `needs_review`, `awaiting_weight` | `needs_review` |
| `logged` | `logged` |
| `failed` | `failed` |
| `discarded` | `discarded` |

A capture belonging to another device returns 404.

**Check:** with a WebSocket client connected, a `curl` upload produces `capture.updated` messages, first for `identifying` and then `logged` or `needs_review`.

---

## Phase 11: Reports

Reports use only entries whose capture status is `logged`, and only nutrients with `is_reported = true`.

**`GET /api/v1/reports/daily?date=YYYY-MM-DD`** (the default is today in the profile timezone):

```json
{
  "date": "2026-11-08",
  "target": {"energy_kcal": 1970, "protein_g": 147.8, "fat_g": 65.7, "carbohydrate_g": 197.0, "floor_applied": false},
  "totals": [{"code": "energy_kcal", "name": "Energy", "unit": "kcal", "amount": 1210.5,
              "entries_with_data": 4, "entries_total": 4}],
  "remaining": {"energy_kcal": 759.5, "protein_g": 81.2, "fat_g": 20.1, "carbohydrate_g": 61.3},
  "entries": [/* log entry shapes */],
  "estimated_entries": 1
}
```

- **`target`:** the latest `nutrition_targets` row with `effective_from` before the end of that local day. Use null if there is none.
- **`entries_with_data`:** shows how many entries had a value for that nutrient. Many dishes lack micronutrients, so totals must show their coverage.
- **`estimated_entries`:** the number of entries with `weight_source = 'user_estimate'`.

**`GET /api/v1/reports/weekly?week_start=YYYY-MM-DD`** returns:
- 7 daily summaries, each with date, energy, protein, fat, carbs and that day's target
- the average of each
- weight entries in that week
- the active goal with `start_weight_kg`, `target_weight_kg` and the latest weight

Do the aggregation in SQL: sum `food_log_entry_nutrients.amount` joined to entries and filtered by user and local date.

**Check:** log three captures, then confirm the daily totals equal the sum of the entry nutrients, and that a target change mid-week shows on the correct days.

---

## Phase 12: Tests, verification and docs

1. **Unit tests** (`tests/`, using `pytest`). These need no database or network:
   - text normalization
   - `compute_nutrition`, including missing nutrients
   - the target calculator cases from phase 5
   - the recognition decision: threshold, unknown codes and empty candidates
   - extraction parsing of `-`, blank and float values (use a tiny in-memory workbook built with openpyxl)
   - curation and alias validation
2. **End-to-end run** against the dev database, where all data is disposable:
   1. Sign up, then complete onboarding.
   2. Create a device.
   3. Upload a device capture of a roti photo with `curl`.
   4. Watch it log.
   5. Upload a phone capture without a weight, then patch the weight.
   6. Use "Wrong food?".
   7. Fetch the daily report.
   8. Delete a capture, and confirm that the local file and the Cloudinary image are gone.
3. `alembic check` passes, and `python -m app.seeds.reference` runs twice without changes.
4. **Update `CLAUDE.md` and `README.md`.** Cover the new structure, the commands (seed, extract, worker and host flags, tests) and the rules from "Rules that change". Remove the notes about `analyses`, the ignored `device_id` and the 409 on device delete.
5. **Update `.env` documentation in `CLAUDE.md`** with the new required variables: `VISION_AI_API_KEY` and `VISION_AI_MODEL`.

### Events to record (`action` values)

`user.onboarded`, `profile.updated`, `weight.recorded`, `goal.set`, `goal.replaced`, `goal.achieved`, `target.calculated`, `device.created`, `device.renamed`, `device.key_rotated`, `device.revoked`, `capture.received`, `capture.recognized`, `capture.recognition_failed`, `capture.image_uploaded`, `capture.image_upload_failed`, `capture.food_selected`, `capture.weight_changed`, `capture.discarded`, `capture.reprocessed`, `capture.deleted`, `entry.created`, `entry.recalculated`, `entry.food_changed`.

---

## Final file layout (new or changed)

```
calop-backend/
  app/
    controllers/  auth_ me_ device_ device_api_ capture_ log_ food_ report_ realtime_ health_controller.py, dependencies.py
    services/     event_ food_ food_text target_calculator profile_ device_ capture_ job_ recognition_ log_ report_ user_service.py
    integrations/ ai/{food_recognizer.py, openai_compatible_food_recognizer.py}, auth/, storage/
    models/       user device capture food log job event (+ __init__.py)
    views/        one module per area
    seeds/        reference.py
    core/         config, database, exceptions, request_context, security
    realtime.py, worker.py, main.py
  data/reference/ source/*.xlsx, extracted/*.csv, curation.csv, aliases.csv
  scripts/        extract_reference_data.py
  tests/
  storage/        (gitignored) local images
```

## Contracts for the firmware and the mobile app

These aren't built in this repo, but the backend must support them exactly.

**ESP32-S3 firmware:**
1. Connect to Wi-Fi. Server URL and API key are firmware config, using the laptop's reserved LAN IP, such as `http://192.168.1.50:8000`.
2. Show the live weight on the OLED. When the weight is stable and above 0, take a JPEG and generate a UUID v4 `capture_id`.
3. `POST /api/v1/device/captures` (multipart) with the headers `X-API-Key` and `X-Firmware-Version`. The OLED shows `SENDING`.
   - On a network error or 5xx, retry with the **same** `capture_id`, showing `RETRY`.
4. On 200 or 202, poll `GET /api/v1/device/captures/{id}/status` every 500 ms for up to 15 seconds:
   - `logged` → `LOGGED`
   - `needs_review` → `CHECK APP`
   - `failed` → `ERROR`
   - timeout → `CHECK APP`
5. Reuse the HTTP connection (keep-alive) between requests.

**Mobile app (React Native, Expo):**
- **Auth:** signup and login, keeping the access and refresh tokens and refreshing them before they expire.
- **Onboarding:** show the questionnaire if `GET /me` returns `onboarding_completed: false`. Submit it to `/me/onboarding`, and show any warnings with their suggested date.
- **Device pairing:** `POST /devices`, then show the API key once for flashing.
- **Phone capture:**
  1. Take the photo with `expo-camera` as a JPEG at full quality, with no resizing. Don't import from the gallery.
  2. Generate a UUID and `POST /captures` immediately.
  3. Ask for the weight while recognition runs, then `PATCH /captures/{id}`.
- **Live updates:** open `WS /api/v1/ws` and send the auth message.
  - On `capture.updated`, update the screen.
  - For `needs_review`, show the candidates, a search box (`GET /foods?q=`) and Discard.
- **Images:** load photos from `GET /captures/{id}/image` with the `Authorization` header.
- **Screens:** today (the daily report), week (the weekly report), history (log entries, with "Wrong food?") and settings (profile, weight, goal, device).
- **Plain HTTP:** the app talks to the server over plain HTTP on the LAN. Expo Go allows this, but standalone builds must enable cleartext traffic.

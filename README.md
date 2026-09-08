# CivicAI — Smart Civic Reporting for Mangaluru

A web application that helps citizens of Mangaluru photograph and report civic issues — potholes, broken streetlights, garbage, drainage problems, water leaks, and more — and automatically routes each report to the correct municipal authority.

---

## Table of Contents

1. [Problem](#problem)
2. [Our Approach](#our-approach)
3. [What Makes CivicAI Different](#what-makes-civicai-different)
4. [Application Flow](#application-flow)
5. [Technical Architecture](#technical-architecture)
6. [AI / Computer-Vision Pipeline](#ai--computer-vision-pipeline)
7. [Civic Classification Categories](#civic-classification-categories)
8. [Privacy and Security](#privacy-and-security)
9. [Evidence Verification and Decision Logic](#evidence-verification-and-decision-logic)
10. [Authority Routing](#authority-routing)
11. [Complaint and Status Workflow](#complaint-and-status-workflow)
12. [Realtime Status Updates](#realtime-status-updates)
13. [API Overview](#api-overview)
14. [Project Structure](#project-structure)
15. [Setup and Run Locally](#setup-and-run-locally)
16. [Testing](#testing)
17. [Challenges We Solved](#challenges-we-solved)
18. [Limitations / Honest Boundaries](#limitations--honest-boundaries)
19. [Demo Scenario](#demo-scenario)
20. [Future Improvements](#future-improvements)
21. [License](#license)

---

## Problem

When a citizen spots a civic issue — a pothole, an overflowing drain, a broken streetlight — they face several barriers to effective reporting:

| Problem | Impact |
|---------|--------|
| Not knowing the correct authority | Reports go to the wrong department and are ignored |
| Unclear or irrelevant photos | Non-civic images (selfies, random photos) create noise in the system |
| Privacy risks in submitted images | Faces and license plates in photos can expose bystanders |
| Duplicate complaints | Multiple citizens reporting the same issue creates administrative clutter |
| No feedback loop | Citizens submit a report and hear nothing back |
| Low credibility of evidence | Reports without GPS, good images, or context are hard to act on |

---

## Our Approach

CivicAI addresses each barrier through an AI-assisted pipeline that runs before a report is stored:

- **AI-assisted image classification** — Groq Vision identifies what kind of civic issue the image shows, so citizens do not need to choose a category manually.
- **Privacy-first processing** — faces and license plates are redacted from the image before it is used by any AI model or stored in the cloud.
- **Civic relevance gate** — selfies, portraits, and non-civic photos are rejected immediately with a clear message.
- **Evidence scoring** — each submission is scored across four dimensions (visual quality, category confidence, GPS quality, freshness) to assess the strength of the evidence.
- **Duplicate and reopen detection** — the pipeline checks whether an active report for the same issue already exists nearby, or whether a previously resolved issue has re-appeared.
- **Authority routing** — the recommended government authority is selected automatically from Mangaluru's authority data based on the issue category and reported location.
- **Citizen review and approval** — the AI result is shown to the citizen before the report is saved, with the option to correct the category, description, or authority.
- **Status tracking and realtime updates** — citizens can follow their report's progress from submission through admin review to resolution.

---

## What Makes CivicAI Different

**Privacy before AI.** Most civic-reporting tools send raw photos to external AI services. CivicAI runs face detection (YuNet ONNX) and licence-plate detection (YOLOv9) *locally* on the server and produces a redacted image before calling any remote API or storing anything. The original unredacted image is stored in a private bucket accessible only to the backend service role; the redacted image is what citizens and admins can access.

**Groq Vision is the final semantic authority.** CivicAI uses a two-level CV approach. A specialist road-damage model (YOLOv8s fine-tuned on RDD2022) runs locally to detect potholes and road cracks. Its result is passed to Groq Vision as a *non-authoritative supporting hint* — the specialist model can narrow the search space but cannot override the semantic judgment of the vision model. This prevents, for example, a garbage scene from being misclassified as road damage simply because road surface is visible behind the rubbish.

**Explainable evidence dimensions.** Instead of a single confidence score, each report carries four dimensions — visual confidence, category confidence, location confidence, and freshness confidence — combined into a weighted evidence score. Admins can see the full evidence breakdown; citizens see a simpler message.

**Duplicate and reopen awareness.** Before saving a new report, the pipeline queries the database for active reports with the same image hash or at the same GPS location. Resolved-issue reopen detection identifies cases where an issue may have returned after being fixed. Both signals are surfaced to the admin with an explicit priority label.

**Citizen approval step.** The AI result is presented to the citizen as a *proposal*, not a final decision. The citizen can edit the category, description, and authority before confirming. This catches AI mistakes without requiring perfect classification.

**Data-driven authority routing.** The routing logic reads from a static JSON file of Mangaluru authorities. There are no hard-coded authority names in the routing algorithm — all rules are data-driven. A specialist tie-break rule ensures that a single-category authority (e.g. MESCOM for streetlights) is preferred over a generic multi-category authority when geographic signals are equal.

---

## Application Flow

### Citizen Journey

```
1.  Open CivicAI in a browser
2.  Sign in via Supabase Auth (email/password)
3.  Tap "Report Issue" → take a photo or pick one from the gallery
4.  Enter the area / location text; optionally use GPS to auto-detect coordinates
5.  Submit → backend validates the image (format, size, minimum resolution)
6.  Backend runs privacy redaction: faces blurred, license plates blurred
7.  Civic relevance gate: selfies and non-civic images are rejected with a clear message
8.  AI pipeline classifies the issue category (Groq Vision as final authority)
9.  Authority routing selects the recommended Mangaluru authority for that category
10. Evidence scoring assesses GPS quality, visual confidence, category certainty, and freshness
11. AI review screen: citizen sees the proposed category, description, authority,
    and a confidence indicator
12. Citizen edits anything that looks wrong, then confirms
13. Report is saved with status SUBMITTED
    (Government submission is outside scope — complaints table exists in the
    schema but the live government submission path is not implemented)
14. Citizen visits "My Reports" to track the report's status
15. When an admin updates the report status, the citizen's report list updates
    automatically via Supabase Realtime
```

### Admin Journey

```
1.  Admin signs in with a JWT that has app_role = "admin"
2.  Admin visits the admin dashboard to see all submitted reports
3.  Admin can filter by category, status, or priority
4.  Each report shows: category, area, AI confidence, evidence score,
    admin priority, and the redacted image URL (15-minute signed URL)
5.  Admin updates the report status: UNDER_REVIEW → RESOLVED / REJECTED / ARCHIVED
6.  Rejection requires a rejection_reason (shown to the citizen)
7.  Status change is written to the database
8.  Supabase Realtime delivers the update to the citizen's browser automatically
```

---

## Technical Architecture

### Frontend

| Technology | Role |
|---|---|
| Next.js 14 (App Router) | React framework; server and client components |
| TypeScript | Full type safety across the frontend |
| Tailwind CSS | Utility-first styling |
| shadcn/ui components (`class-variance-authority`, `clsx`) | UI primitives |
| `@supabase/supabase-js` | Auth, Realtime subscriptions |
| Browser `navigator.geolocation` | GPS coordinate capture |
| Browser `MediaDevices` API | In-browser camera access |
| Browser `SpeechRecognition` API | Optional voice input for description |

**Pages:**
- `/login` — email/password sign-in
- `/report/new` — two-stage report creation (photo capture → AI review)
- `/reports` — citizen's own report list with realtime status updates
- `/reports/[id]` — single report detail view
- `/admin` — admin dashboard

There is no PWA manifest, no service worker, and no IndexedDB in the current codebase.

### Backend

| Technology | Role |
|---|---|
| FastAPI (0.111.x) | REST API framework |
| Python 3.11+ | Runtime |
| Uvicorn | ASGI server |
| slowapi | Per-endpoint rate limiting (10 req/min for AI endpoint) |
| Pydantic v2 | Request/response schemas, validation |
| `python-jose` | JWT verification against Supabase JWKS |
| supabase-py | Database and storage client |
| Pillow | Image processing |
| OpenCV (`opencv-python-headless`) | Face detection (YuNet) |
| ultralytics (YOLOv8) | General object detection (COCO-80) + road-damage specialist |
| open-image-models + fast-alpr | License plate detection (YOLOv9) |
| groq (Python SDK) | Groq Vision API client |
| blake3 | Image hashing for duplicate detection |
| sentence-transformers | RAG embedding (installed; RAG tests require model download) |
| tiktoken | Token counting for text chunking |
| psutil | RAM check before model loading |

**Key backend modules:**

```
cv/pipeline.py          — orchestrates all pipeline steps end-to-end
cv/image_validator.py   — format, size, resolution validation
cv/privacy.py           — face + plate redaction
cv/relevance.py         — civic relevance / selfie rejection gate
cv/detection.py         — YOLOv8n general object detection (COCO-80)
cv/road_damage.py       — YOLOv8s RDD2022 specialist road-damage model
cv/evidence_scorer.py   — weighted evidence score computation
cv/decision_engine.py   — duplicate/reopen detection + admin priority
llm/groq_provider.py    — Groq Vision API call + JSON extraction
llm/fallback_provider.py— heuristic fallback when Groq is unavailable
llm/prompts.py          — prompt templates + injection sanitization
llm/output_validator.py — LLM response validation
services/authority_service.py — authority routing
services/report_service.py    — report creation and retrieval
services/storage_service.py   — Supabase Storage signed URL generation
```

### Data

| Component | Role |
|---|---|
| Supabase (hosted PostgreSQL) | Primary database |
| PostGIS `GEOGRAPHY(POINT, 4326)` | GPS coordinates stored per report; used for geo-proximity queries |
| `report-originals` bucket | Private; original unredacted images; service role only |
| `report-redacted` bucket | Private; privacy-processed images; 15-minute signed URLs for citizens/admins |
| Row-Level Security (RLS) | Citizens see only their own reports; admins see all |
| Supabase Realtime | `postgres_changes` on `reports` table; UPDATE events delivered to subscribers |
| 12 SQL migrations | Applied in order; all idempotent |
| Authority seed (`001_authorities.sql`) | Mangaluru authorities seeded from static data |
| RTI knowledge base seed (`002_rti_knowledge_base.sql`) | Knowledge chunks seeded for a future RTI draft generation feature (not operational in current version) |

---

## AI / Computer-Vision Pipeline

Each image submitted by a citizen passes through the following sequential steps:

```
Upload
  │
  ▼
Step 1 — Validation
  Checks format (JPEG/PNG/WebP/GIF → converted to JPEG),
  file size (≤ 10 MB), and minimum pixel dimensions.
  Raises HTTP 422 on failure.
  │
  ▼
Step 2 — Privacy Redaction
  YuNet ONNX face detector → Gaussian blur (radius 20) over each face.
  YOLOv9 licence-plate detector → Gaussian blur (radius 20) over each plate.
  Produces a redacted JPEG. All downstream steps use the redacted image.
  The original is stored privately; the redacted image is what is accessible.
  │
  ▼
Step 3 — Image Hashing (BLAKE3)
  Hash of the validated (pre-redaction) bytes for duplicate detection.
  │
  ▼
Step 4 — Duplicate Check (advisory)
  Checks active reports for the same image hash.
  │
  ▼
Step 5 — YOLO General Detection (COCO-80)
  YOLOv8n detects objects to build an initial category signal and
  populate the `all_class_names` list used by the relevance gate.
  │
  ▼
Step 6 — Civic Relevance Gate
  Rejects images that are dominated by person detections with no
  civic-infrastructure objects present (selfies, portraits).
  Raises HTTP 422 with a clear user-facing message.
  │
  ▼
Step 7 — Road-Damage Specialist Model (YOLOv8s / RDD2022)
  Detects potholes (D40) and road cracks (D00/D10/D20).
  Result is a NON-AUTHORITATIVE hint: if the specialist detects road
  damage confidently, that hint is passed to Groq Vision as context.
  The specialist result NEVER overrides the Groq Vision decision.
  │
  ▼
Step 8 — Groq Vision Semantic Classification
  The redacted JPEG (base64) is sent to Groq Vision
  (model: qwen/qwen3.8-27b) with a structured prompt.
  The prompt explicitly names the DB enum categories and includes
  disambiguation rules (e.g. "if primary subject is garbage, classify
  as garbage_overflow even if road surface is visible").
  Groq Vision is the FINAL semantic authority for the category.
  │
  ▼
Step 8b — Fallback (if Groq unavailable)
  Heuristic classification from YOLO class names + address keywords.
  Used when GROQ_API_KEY is absent or the API call fails.
  │
  ▼
Step 9 — Category Normalization
  The raw Groq output is normalized to a canonical IssueCategory
  enum value. Synonyms and alternative phrasings are mapped.
  │
  ▼
Step 10 — Evidence Scoring + Decision Engine
  Four confidence dimensions are computed:
    visual (0.35)     — AI detection confidence
    category (0.20)   — model certainty about the category
    location (0.30)   — GPS quality and Mangaluru plausibility
    freshness (0.15)  — temporal recency signal
  Weighted sum → evidence_score [0.0, 1.0].
  Decision engine checks for duplicates, reopens, and insufficient evidence.
  Assigns admin_priority (CRITICAL / HIGH / MEDIUM / LOW / REOPEN_REVIEW /
  DUPLICATE / INSUFFICIENT).
  │
  ▼
Step 11 — Authority Routing
  Routes to the correct Mangaluru authority based on the Vision-classified
  category (not the YOLO category) and the reported area text.
  │
  ▼
AIResult returned to the API layer → stored in Supabase → shown to citizen
```

**Invalid image handling:** If the image fails validation or the civic relevance gate, the API returns HTTP 422 and nothing is stored. Non-civic images (e.g. selfies) are rejected at Step 6.

**Fallback behavior:** If Groq Vision is unavailable (no API key, network failure, timeout), the pipeline uses a keyword-based heuristic that maps YOLO class names and address text to a category. The `llm_provider_used` field in the response indicates which path was taken.

---

## Civic Classification Categories

These are the exact `IssueCategory` enum values used throughout the database, API, and frontend:

| Value | Label | Typical examples |
|---|---|---|
| `pothole` | Pothole | Hole in road surface, sunken patch |
| `road_damage` | Road Damage | Cracks, alligator cracking, severe surface deterioration |
| `broken_streetlight` | Broken Streetlight | Damaged lamp, dangling fixture, dead pole |
| `garbage_overflow` | Garbage Overflow | Overflowing bins, roadside dump, illegal waste pile |
| `open_drain` | Open Drain | Uncovered or blocked drainage channel |
| `illegal_construction` | Illegal Construction | Unauthorized building, encroachment |
| `waterlogging` | Waterlogging | Standing water, flooded road |
| `water_supply` | Water Supply Issue | Burst pipe, water main leak |
| `sewage` | Sewage Problem | Sewage discharge, overflowing manhole |
| `other` | Other | Civic issue not fitting the above categories |

The category `invalid` is used internally during AI processing to signal a non-civic image and is never stored in the database.

---

## Privacy and Security

### Image Privacy

- **Faces** are blurred with Gaussian blur (radius 20) using a YuNet ONNX model before the image is sent to Groq Vision or stored.
- **License plates** are blurred using a YOLOv9 model (open-image-models) before the image is sent to Groq Vision or stored.
- Both models run locally on the backend server. No raw face or plate pixels are sent to external services.
- The **original image** is stored in the `report-originals` private Supabase bucket. Only the backend service role can access it. There are no public or citizen-accessible URLs for original images.
- The **redacted image** is stored in the `report-redacted` private bucket. Citizens and admins access it via **15-minute signed URLs** generated by the backend service role. The URL expires automatically.
- Evidence disclaimer: evidence scores reflect the strength of submitted evidence only, not a verified assessment of real-world conditions.

### Authentication and Authorization

- All API endpoints (except `/api/v1/health`) require a valid JWT issued by Supabase Auth.
- JWTs are verified server-side using the Supabase JWKS endpoint. The JWKS cache is pre-warmed at startup.
- Role-based access control: citizens see and modify only their own reports (IDOR protection enforced in every endpoint). Admins bypass ownership checks via `app_role = "admin"` in the JWT.
- Row-Level Security (RLS) is enabled on all Supabase tables. Citizens can only read their own rows.
- Rate limiting: the AI pipeline endpoint is limited to 10 requests per minute per IP.
- Input sanitization: all citizen-supplied text is sanitized before injection into LLM prompts (injection-pattern removal + 2,000-character cap).

### What Must Never Be Committed

```
backend/.env               — SUPABASE_URL, SUPABASE_SERVICE_KEY, GROQ_API_KEY
frontend/.env.local        — NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
```

Both files are listed in `.gitignore`. The repository contains only `.env.example` and `.env.local.example` with placeholder values.

---

## Evidence Verification and Decision Logic

CivicAI does not treat an AI prediction as absolute truth. Each submission is assessed across four evidence dimensions:

| Dimension | Weight | What it measures |
|---|---|---|
| Visual | 0.35 | AI detection confidence from image analysis |
| Category | 0.20 | Model certainty about the civic category |
| Location | 0.30 | GPS quality, Mangaluru bounding-box plausibility |
| Freshness | 0.15 | Temporal recency of the submission |

**Formula:** `evidence_score = visual×0.35 + category×0.20 + location×0.30 + freshness×0.15`

**Decision thresholds (from `cv/evidence_scorer.py`):**

| Threshold | Value | Meaning |
|---|---|---|
| `VALID_THRESHOLD` | 0.65 | Score ≥ 0.65 → `valid_civic_report` |
| `REVIEW_THRESHOLD` | 0.35 | Score ≥ 0.35 → `needs_admin_review` |
| Below review threshold | — | `insufficient_evidence` |

**Decision states (`DecisionState` enum):**

| State | Meaning |
|---|---|
| `valid_civic_report` | Strong evidence; actionable |
| `needs_admin_review` | Moderate evidence; admin should review |
| `insufficient_evidence` | Weak evidence; unlikely to be actionable |
| `duplicate_active_report` | Same issue already reported nearby and is active |
| `possible_reopened_issue` | Issue appears to have returned after being resolved |
| `invalid_image` | Image failed validation or civic relevance gate |

**Admin priority labels (`AdminPriority` enum):**
`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `REOPEN_REVIEW`, `DUPLICATE`, `INSUFFICIENT`

**Duplicate detection:** Checks active reports within 50 metres at the same GPS coordinates with the same category, or with the same BLAKE3 image hash.

**Reopen detection:** Checks resolved reports within 50 metres, resolved within the past 60 days, where visual and freshness confidence exceed minimum thresholds.

**Image reuse flag:** If the same image hash appears in a historical (non-active) report, an `image_reuse_flag` is set. This is an admin signal, not a rejection.

---

## Authority Routing

Authority data is loaded from `backend/data/mangaluru_authorities.json` — a static, immutable file. Routing follows four rules in order:

1. **Filter by category** — only authorities that handle the issue category are considered.
2. **Keyword match on area text** — if the reported area text contains words that appear in an authority's jurisdiction description, that authority is selected (confidence 1.0).
3. **Singleton-specialist tie-break** — if no keyword match, the authority whose category list contains exactly one entry is preferred. This rule is fully data-driven (no authority names are hard-coded). Example: MESCOM handles only `broken_streetlight`, so it wins over MCC (which handles 7 categories) when a streetlight issue is reported with no geographic signal.
4. **Generic fallback** — first category-matching authority in JSON order (confidence 0.7).

**Authorities in Mangaluru (from the seed data):**

| ID | Short Name | Typical Categories |
|---|---|---|
| auth-001 | MCC | Multiple categories including pothole, road_damage, garbage_overflow |
| auth-002 | MCC North | Zone-specific subset |
| auth-003 | MWWD | water_supply, sewage |
| auth-004 | NHAI Mangaluru | pothole, road_damage (national highways) |
| auth-005 | MESCOM | broken_streetlight (sole dedicated authority) |
| auth-006 | MUDA | illegal_construction |
| auth-007 | MCC Drainage | open_drain, waterlogging |

Authority routing uses the **Vision-classified category** (the final Groq result), not the preliminary YOLO category.

---

## Complaint and Status Workflow

Reports follow a state machine enforced by both the API and the database schema:

```
                   ┌─────────────┐
                   │  SUBMITTED  │◄── created by citizen
                   └──────┬──────┘
                          │  admin acts
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        UNDER_REVIEW   REJECTED    ARCHIVED
              │           │
         ┌────┴──┐        ▼
         ▼       ▼     ARCHIVED
      RESOLVED REJECTED
         │       │
         ▼       ▼
      ARCHIVED ARCHIVED
```

**Valid transitions (admin-only):**

| From | Allowed next states |
|---|---|
| `SUBMITTED` | `UNDER_REVIEW`, `REJECTED`, `ARCHIVED` |
| `UNDER_REVIEW` | `RESOLVED`, `REJECTED`, `ARCHIVED` |
| `RESOLVED` | `ARCHIVED` |
| `REJECTED` | `ARCHIVED` |
| `ARCHIVED` | *(terminal — no further transitions)* |

- `REJECTED` requires a `rejection_reason` (shown to the citizen).
- Invalid status transitions return HTTP 422.
- Citizens cannot change the status — only admins can.

The database also contains a `complaints` table and an `rti_requests` table in the schema. Neither government complaint submission nor RTI functionality is implemented in the current version — both are future scope.

---

## Realtime Status Updates

When an admin changes a report's status, the citizen's browser updates automatically:

```
Admin updates status via PATCH /api/v1/admin/reports/{id}/status
  │
  ▼
Database write (Supabase PostgreSQL)
  │
  ▼
Supabase Realtime (postgres_changes publication on reports table)
  │  Migration 008 adds reports to the supabase_realtime publication
  ▼
Event delivered to the citizen's browser via WebSocket
  │
  ▼
Frontend re-fetches the report list from the backend API
  │
  ▼
Citizen sees updated status and any rejection reason in "My Reports"
```

The subscription listens for `UPDATE` events on the `reports` table. On receiving an event the frontend re-fetches from the backend to get the authoritative persisted value rather than trusting the realtime payload directly.

---

## API Overview

All routes are prefixed with `/api/v1`.

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` |

### Reports (citizen)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/reports/` | JWT | Create report. Triggers AI pipeline when photo is uploaded without category/description. Rate-limited to 10/min. |
| `PATCH` | `/reports/{id}` | JWT (owner) | Citizen confirms/edits AI result (category, description, authority). |
| `GET` | `/reports/` | JWT | List caller's own reports (admins see all). |
| `GET` | `/reports/{id}` | JWT (owner) | Get single report with signed image URLs. |

**Path selection for `POST /reports/`:**
- Photo uploaded + no category/description → AI pipeline path
- Category + description provided → text-based path (backward-compatible)

### Admin

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/admin/reports` | Admin JWT | List all reports |
| `GET` | `/admin/stats` | Admin JWT | Aggregate statistics by category, status, authority |
| `PATCH` | `/admin/reports/{id}/status` | Admin JWT | Update report status (enforces state machine) |
| `GET` | `/admin/reports/{id}/evidence` | Admin JWT | Full evidence breakdown (scores, dimensions, reasoning) |
| `GET` | `/admin/reports/{id}/links` | Admin JWT | Supporting evidence links (duplicates/reopens) |

---

## Project Structure

```
CivicAI/
├── frontend/                  # Next.js 14 frontend
│   ├── app/
│   │   ├── login/             # Login page
│   │   ├── report/new/        # Two-stage report creation
│   │   ├── reports/           # My reports list (realtime)
│   │   └── reports/[id]/      # Report detail
│   ├── components/
│   │   ├── Header.tsx
│   │   └── StatusBadge.tsx
│   ├── lib/
│   │   ├── api.ts             # Backend API client
│   │   ├── constants.ts       # Categories, status labels, authority list
│   │   ├── supabase.ts        # Supabase browser client
│   │   └── utils.ts
│   ├── .env.local.example     # Required env vars (no secrets)
│   └── package.json
│
├── backend/                   # FastAPI backend
│   ├── cv/
│   │   ├── pipeline.py        # Main AI pipeline orchestrator
│   │   ├── image_validator.py
│   │   ├── privacy.py         # Face + plate redaction
│   │   ├── relevance.py       # Selfie rejection gate
│   │   ├── detection.py       # YOLOv8n COCO detection
│   │   ├── road_damage.py     # YOLOv8s RDD2022 specialist
│   │   ├── evidence_scorer.py # Weighted evidence score
│   │   ├── decision_engine.py # Duplicate/reopen/priority logic
│   │   └── confidence.py
│   ├── llm/
│   │   ├── groq_provider.py   # Groq Vision API integration
│   │   ├── fallback_provider.py
│   │   ├── prompts.py         # Prompt templates + injection sanitization
│   │   └── output_validator.py
│   ├── routers/
│   │   ├── health.py
│   │   ├── reports.py         # Citizen report endpoints
│   │   └── admin.py           # Admin endpoints
│   ├── services/
│   │   ├── authority_service.py
│   │   ├── report_service.py
│   │   ├── llm_service.py
│   │   └── storage_service.py
│   ├── schemas/report.py      # Pydantic schemas + IssueCategory enum
│   ├── db/
│   │   ├── supabase_client.py
│   │   └── repositories/
│   ├── data/
│   │   └── mangaluru_authorities.json   # Static authority data (immutable)
│   ├── rag/                   # RAG embedder/retriever (sentence-transformers)
│   ├── security/              # JWT verify, RBAC, input sanitizer
│   ├── .env.example           # Required env vars (no secrets)
│   ├── main.py                # FastAPI app entry point
│   ├── requirements.txt
│   └── pytest.ini
│
├── supabase/
│   ├── migrations/            # 12 SQL migrations (applied in order)
│   └── seed/                  # Authority data + RTI knowledge base
│
├── docs/                      # Architecture documents
├── render.yaml                # Render.com deployment config (backend)
├── vercel.json                # Vercel deployment config (frontend)
└── README.md
```

---

## Setup and Run Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Supabase project (free tier works)
- A Groq API key (free tier available at console.groq.com)

### 1. Clone the repository

```bash
git clone https://github.com/AkshathaN-05/CivicAI.git
cd CivicAI
```

### 2. Supabase setup

1. Create a new Supabase project.
2. In the Supabase SQL Editor, run the migrations in order:
   ```
   supabase/migrations/001_enums.sql
   supabase/migrations/002_tables.sql
   supabase/migrations/003_indexes.sql
   supabase/migrations/004_rls.sql
   supabase/migrations/005_audit_trigger.sql
   supabase/migrations/006_auth_trigger.sql
   supabase/migrations/007_report_status.sql
   supabase/migrations/008_realtime_reports.sql
   supabase/migrations/009_storage_buckets.sql
   supabase/migrations/010_evidence_fields.sql
   supabase/migrations/011_report_links.sql
   supabase/migrations/012_evidence_rpc_functions.sql
   ```
3. Run the seed files:
   ```
   supabase/seed/001_authorities.sql
   supabase/seed/002_rti_knowledge_base.sql
   ```
4. Enable Realtime for the `reports` table in the Supabase dashboard (migration 008 handles the publication).

### 3. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env` (never commit this file):

```
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
GROQ_API_KEY=your_groq_api_key
ALLOWED_ORIGINS=http://localhost:3000
ENV=development
DEMO_USER_ID=
```

Start the backend:

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `http://127.0.0.1:8000/api/v1/health`

### 4. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local` (never commit this file):

```
NEXT_PUBLIC_SUPABASE_URL=your_supabase_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start the frontend:

```bash
cd frontend
npm run dev
```

Open: `http://localhost:3000`

### 5. Required environment variable names (reference)

| File | Variable | Purpose |
|---|---|---|
| `backend/.env` | `SUPABASE_URL` | Supabase project URL |
| `backend/.env` | `SUPABASE_SERVICE_KEY` | Supabase service role key (server-side only) |
| `backend/.env` | `GROQ_API_KEY` | Groq API key for Vision classification |
| `backend/.env` | `ALLOWED_ORIGINS` | Comma-separated allowed CORS origins |
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL (public) |
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (public) |
| `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL` | Backend base URL |

---

## Testing

### Run classification and pipeline tests

```bash
cd backend
python -m pytest tests/test_civic_classification.py tests/test_pipeline.py -q
```

### Run full backend test suite

```bash
cd backend
python -m pytest -q
```

### Frontend type check

```bash
cd frontend
npx tsc --noEmit
```

### Latest verified results

| Check | Result |
|---|---|
| `test_civic_classification.py` + `test_pipeline.py` | **263 passed** |
| Full backend pytest | **1018 passed, 3 pre-existing failures** |
| `npx tsc --noEmit` | **Clean** |

**Known pre-existing failures:** The 3 failing tests are in `tests/test_rag.py` (`TestEmbedder`). They fail because `sentence_transformers` requires a model download (`all-MiniLM-L6-v2`) that is not present in the local environment. These failures are unrelated to the classification pipeline and do not affect the core civic-reporting functionality.

---

## Challenges We Solved

### 1. Garbage misclassified as road damage
A road-visible scene behind a garbage dump caused the specialist road-damage model to fire, and the old prompt treated that as strong evidence for `road_damage`. **Fix:** The road model hint is now explicitly labeled as `[NON-AUTHORITATIVE]` in the prompt. Groq Vision was instructed that if the primary subject of the image is garbage, the correct category is `garbage_overflow` regardless of any road surface visible behind it.

### 2. Broken streetlight classified as `other`
`qwen/qwen3.8-27b` is a chain-of-thought model that produces `<think>...</think>` blocks before its JSON output. The original JSON extractor used a greedy regex that matched the *first* `{...}` in the response, which could be a partial JSON fragment inside the reasoning chain. **Fix:** Think blocks are stripped before extraction; the extractor now iterates all JSON candidates in reverse and takes the last valid one — the actual answer.

### 3. Generic object detection misreading scene context
YOLOv8n COCO sees objects, not civic issues. A bottle becomes `garbage_overflow`, a car becomes `road_damage` in simplistic mappings. The specialist road-damage model (RDD2022) added specificity for road issues, and Groq Vision provides semantic understanding for all other categories.

### 4. Selfie and non-civic image rejection
The civic relevance gate uses the full set of YOLO-detected class names. A selfie is rejected only when persons are detected with no civic-infrastructure objects present. A road scene with pedestrians is accepted. The threshold was tuned to catch frontal selfies (YOLO confidence ≥ 0.20) without rejecting civic scenes containing people.

### 5. Authority routing ambiguity
When multiple authorities handle the same category, the original fallback simply returned the first match. For `broken_streetlight`, this could return MCC before MESCOM. The singleton-specialist tie-break ensures the most specific (fewest categories) authority wins when geographic signals are absent, without hard-coding any authority name.

### 6. Privacy before AI
Sending raw civic photos to a remote API risks exposing bystander faces and vehicle plates. Both redaction models run on the backend server before any external call. Groq Vision receives only the redacted image.

### 7. Database status state machine enforcement
Invalid admin status transitions (e.g. `ARCHIVED → RESOLVED`) must be prevented. The `STATUS_TRANSITIONS` dict in `schemas/report.py` defines all valid transitions, and the service layer raises HTTP 422 for any attempt to move a report to an invalid next state.

### 8. Supabase Realtime subscription management
React Strict Mode fires effects twice in development, which caused duplicate Supabase Realtime channel errors ("cannot add postgres_changes callbacks after subscribe()"). The fix uses a unique timestamp-suffixed channel name per effect invocation so each run creates a fresh channel, and the cleanup function reliably removes it.

---

## Limitations / Honest Boundaries

CivicAI provides AI-assisted evidence assessment. It cannot verify real-world facts from an image alone.

| Claim | Reality |
|---|---|
| "This road is damaged" | The AI identified visual patterns consistent with road damage in the submitted image. The road may have been repaired since, or the image may not represent the current state. |
| "This issue is at the reported location" | GPS coordinates are provided by the citizen's browser. The system cannot verify that the photo was taken at that location. |
| "This issue still exists" | There is no mechanism to confirm a civic issue persists after the photo was taken. |
| "This report is a duplicate" | Duplicate detection is based on image hash and GPS proximity. Two different photos of the same issue will not be flagged as duplicates by hash alone. |
| "This repair failed" | Reopen detection identifies visual similarity near a recently resolved location, but cannot verify that a repair was performed or that it failed. |
| "Evidence score = real-world severity" | The evidence score measures the quality and consistency of the submitted evidence, not the actual severity of the civic issue. |
| "Government submission" | The live government portal submission path is not implemented. The `complaints` and `rti_requests` tables exist in the schema but submission to any government API is outside the current scope. |

---

## Demo Scenario

A citizen in Mangaluru notices a broken streetlight near Hampankatta and wants to report it.

1. They open CivicAI and sign in.
2. They photograph the broken streetlight (wooden pole, dangling lamp).
3. They enter "Hampankatta, Mangaluru" as the area and tap Submit.
4. The backend validates the image, runs face/plate redaction (none found), confirms the image passes the civic relevance gate.
5. The road-damage specialist model detects no road damage — passes a blank hint.
6. Groq Vision receives the redacted image and classifies it as `broken_streetlight` with high confidence.
7. Authority routing: `broken_streetlight` → MESCOM is the sole dedicated authority → selected with confidence 0.8.
8. The AI review screen shows: **Broken Streetlight**, description generated by Groq, **MESCOM** as recommended authority.
9. The citizen confirms (or edits the description) and submits.
10. The report is saved with status `SUBMITTED`.
11. An admin logs into the admin dashboard, reviews the evidence, and moves the status to `UNDER_REVIEW`.
12. The citizen's "My Reports" page shows "Under Review" automatically — no page refresh needed.
13. When the issue is fixed, the admin marks the report `RESOLVED`.
14. The citizen sees "Resolved" in their report list.

*This describes the intended application workflow. Government portal submission and RTI are not implemented in the current version.*

---

## Future Improvements

- **Stronger civic-specific vision models** — fine-tune a model on Indian civic-issue imagery rather than relying on a general-purpose vision LLM.
- **Production government API integrations** — connect to actual Mangaluru municipal APIs for complaint submission and status synchronization.
- **Richer geospatial verification** — use PostGIS polygon containment to verify that a reported location falls within a specific authority's jurisdiction boundary.
- **Background sync for drafts** — allow citizens to start a report offline and sync it when connectivity is restored (currently no offline support is implemented).
- **Improved multilingual support** — the UI and AI prompts are in English; support for Kannada and Tulu would improve accessibility for local citizens.
- **Stronger historical issue intelligence** — build a trend layer that identifies roads or areas with repeatedly reported issues across multiple submissions over time.
- **RTI (Right to Information) integration** — CivicAI could identify cases where a civic issue has remained unresolved long enough to warrant an RTI request, guide citizens in preparing one, and in future versions integrate with official RTI portals. The `rti_requests` table and `rti_knowledge_base` seed data are present in the schema as a foundation for this future feature. This is not part of the current implemented workflow.
- **Confidence calibration** — validate and recalibrate the evidence score thresholds against a labelled dataset of real civic reports.

---

## License

No license file is present in the repository. All rights are retained by the author(s) unless a license is added. If you wish to use or contribute to this project, contact the repository owner.

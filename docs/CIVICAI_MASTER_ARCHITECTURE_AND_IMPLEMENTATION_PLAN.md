# CivicAI — Master Architecture and Implementation Plan
**Version:** 2.0 (Final Approved)
**Status:** LOCKED — Do not modify without an ADR
**Jurisdiction:** Mangaluru, Karnataka, India
**Budget:** ₹0 / $0
**Document type:** Canonical master document — architecture + execution plan

---

# PART A — MASTER ARCHITECTURE

> **LOCKED.** All decisions in this section are approved and immutable.
> Do not modify without filing an Architecture Decision Record (ADR).

---

## Table of Contents — Part A

1. [Executive Summary](#1-executive-summary)
2. [Final Technology Stack](#2-final-technology-stack)
3. [Technology Selection Rationale](#3-technology-selection-rationale)
4. [Overall System Architecture](#4-overall-system-architecture)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Backend Architecture](#6-backend-architecture)
7. [Database Architecture](#7-database-architecture)
8. [AI/CV Architecture](#8-aicv-architecture)
9. [LLM Architecture](#9-llm-architecture)
10. [RAG Architecture](#10-rag-architecture)
11. [Mapping/Geospatial Architecture](#11-mappinggeospatial-architecture)
12. [Mangaluru Authority-Routing Architecture](#12-mangaluru-authority-routing-architecture)
13. [Security Architecture](#13-security-architecture)
14. [Privacy Architecture](#14-privacy-architecture)
15. [Complaint Lifecycle](#15-complaint-lifecycle)
16. [RTI Lifecycle](#16-rti-lifecycle)
17. [Offline/PWA Architecture](#17-offlinepwa-architecture)
18. [API Architecture](#18-api-architecture)
19. [Authentication and Authorization](#19-authentication-and-authorization)
20. [Storage Architecture](#20-storage-architecture)
21. [Database / ER Design](#21-database--er-design)
22. [Data Flow](#22-data-flow)
23. [AI Flow](#23-ai-flow)
24. [Complaint State Machine](#24-complaint-state-machine)
25. [RTI State Machine](#25-rti-state-machine)
26. [Deployment Architecture](#26-deployment-architecture)
27. [Testing Strategy](#27-testing-strategy)
28. [Threat Model](#28-threat-model)
29. [Performance Strategy](#29-performance-strategy)
30. [Free-Tier / Cost Analysis](#30-free-tier--cost-analysis)
31. [Five-Member Team Division](#31-five-member-team-division)
32. [Hackathon Demo Flow](#32-hackathon-demo-flow)
33. [Risks and Mitigations](#33-risks-and-mitigations)
34. [Explicit Out-of-Scope Features](#34-explicit-out-of-scope-features)
35. [Changes from Previous Architecture](#35-changes-from-previous-architecture)
36. [Final Project / Module Structure](#36-final-project--module-structure)
37. [Final Approval Checklist](#37-final-approval-checklist)
38. [Fixed Requirements](#38-fixed-requirements)
39. [Technical Decisions Made](#39-technical-decisions-made)
40. [Unresolved Decisions Requiring Approval](#40-unresolved-decisions-requiring-approval)

---

## 1. Executive Summary

CivicAI is a zero-cost Progressive Web Application for civic issue reporting in Mangaluru, Karnataka. Citizens photograph civic problems using their device camera. An AI pipeline classifies the issue, estimates evidence confidence, detects duplicates, redacts privacy-sensitive content, and recommends the correct Mangaluru authority. The citizen reviews every AI recommendation, corrects if needed, and approves before submission. After 30 days of no government progress, an RTI (Right to Information) flow becomes available — AI drafts the RTI, citizen reviews and approves, and a mock submission is made.

**Core principles:**
- Zero cost — every service used is genuinely free at hackathon scale
- Camera-first — fresh photo capture only, no gallery upload in main flow
- AI assists, citizen decides — no automated submission ever
- Authority data is immutable — the provided Mangaluru JSON is the source of truth
- Security is primary — not an afterthought
- Privacy by design — faces and plates are redacted before any public storage
- Offline-first PWA — complaints survive connectivity loss with clear state labels

---

## 2. Final Technology Stack

### Frontend
| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | Next.js (App Router) | 14.x |
| Language | TypeScript | 5.x |
| Styling | Tailwind CSS | 3.x |
| Component library | shadcn/ui | latest |
| Map rendering | MapLibre GL JS | 4.x |
| Map tiles | OpenFreeMap (openfreemap.org) | free |
| PWA | next-pwa (serwist) | latest |
| Offline storage | idb-keyval (IndexedDB) | latest |
| State management | React Context + SWR | latest |
| Form validation | Zod + react-hook-form | latest |

### Backend
| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | FastAPI | 0.111.x |
| Language | Python | 3.11 |
| ASGI server | Uvicorn | latest |
| Rate limiting | slowapi | latest |
| HTTP client | httpx | latest |
| Image processing | Pillow | latest |
| File hashing | blake3 | latest |

### Database
| Layer | Technology |
|-------|-----------|
| Platform | Supabase (ap-south-1 / Mumbai) |
| Engine | PostgreSQL 15 |
| Spatial extension | PostGIS |
| Vector extension | pgvector |
| Auth | Supabase Auth (JWT) |
| Storage | Supabase Storage |
| Realtime | Supabase Realtime |

### AI / CV
| Component | Technology | Notes |
|-----------|-----------|-------|
| Object detection | YOLOv8n (Ultralytics) | ~30 MB, CPU |
| Face detection | YuNet ONNX (OpenCV) | ~5 MB, CPU |
| Licence plate detection | fast-alpr | ~80 MB, CPU |
| Embedding model | BAAI/bge-large-en-v1.5 | ~440 MB; disabled if RAM <512 MB |
| LLM primary | Groq API (llama-3.1-8b-instant) | free allowance |
| LLM fallback | Deterministic template engine | no external dependency |
| LLM stub | IBM Watsonx provider stub | not wired — future use |

### Infrastructure
| Component | Service | Cost |
|-----------|---------|------|
| Frontend hosting | Vercel (Hobby) | Free |
| Backend hosting | Render (free web service) | Free |
| Database | Supabase (free tier) | Free |
| Keep-alive | cron-job.org | Free |
| CI/CD | GitHub Actions | Free |

---

## 3. Technology Selection Rationale

| Decision | Rationale |
|----------|-----------|
| Next.js App Router | SSR, file-based routing, built-in image optimization, Vercel native |
| FastAPI | Async-native, Pydantic validation, OpenAPI auto-docs, Python AI ecosystem |
| Supabase | Free PostgreSQL + Auth + Storage + Realtime in one platform, Mumbai region |
| PostGIS | Required for geospatial proximity queries on complaint locations |
| pgvector | Required for RAG semantic search on RTI knowledge base |
| YOLOv8n | Lightest YOLO model (~30 MB), CPU-only, no GPU needed |
| YuNet ONNX | Lightweight face detector (5 MB), integrates with OpenCV |
| fast-alpr | Licence plate detection without cloud dependency |
| BAAI/bge-large-en-v1.5 | Best free embedding model for semantic search; RAM-gated |
| Groq API | Free tier LLM inference, fast, no cost at hackathon scale |
| MapLibre GL JS | Open-source, no API key, works with OpenFreeMap tiles |
| Render free tier | Zero-cost backend hosting with 512 MB RAM constraint |
| idb-keyval | Minimal IndexedDB abstraction for offline draft storage |

---

## 4. Overall System Architecture

```
Citizen Device (PWA)
    ↓ HTTPS
Next.js Frontend (Vercel)
    ↓ REST API calls (JWT Bearer)
FastAPI Backend (Render)
    ├── AI/CV Pipeline (YOLOv8n, YuNet, fast-alpr, BAAI embeddings)
    ├── LLM Layer (Groq primary → deterministic fallback)
    ├── Supabase Client (service role for writes, anon for reads)
    └── Authority Router (immutable Mangaluru JSON)
        ↓
Supabase (ap-south-1)
    ├── PostgreSQL 15 (PostGIS + pgvector)
    ├── Supabase Auth (JWT)
    ├── Supabase Storage (private buckets, signed URLs)
    └── Supabase Realtime (status updates)
```

**Key invariants:**
- No AI model is loaded at startup — all models are lazy-loaded per request
- No image is stored in public storage before privacy redaction
- No complaint is submitted without explicit citizen approval
- No RTI is filed without explicit citizen approval
- All government submission is mock-only (no real government API)
- Authority data is read from a static JSON file — never from the database

---

## 5. Frontend Architecture

**Framework:** Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui

**Route structure:**
```
app/
  (auth)/login/          — Supabase Auth UI
  (auth)/register/
  dashboard/             — Complaint list, status overview
  report/new/            — Camera → AI → Review → Submit flow
  report/[id]/           — Complaint detail + status timeline
  report/[id]/rti/       — RTI draft + review + approve
  admin/                 — Admin screens (authority role only)
  api/                   — Next.js API routes (thin proxy only)
```

**State management:** React Context for auth session; SWR for server data; no Redux.

**Offline behaviour:** IndexedDB (idb-keyval) stores draft complaints as `DRAFT_OFFLINE`. On reconnect the citizen manually retries — no background sync.

**PWA:** next-pwa (serwist) generates service worker. App shell cached. API calls are network-first with no offline fallback for API responses.

---

## 6. Backend Architecture

**Framework:** FastAPI 0.111.x, Python 3.11, Uvicorn

**Module structure:**
```
backend/
  main.py                — App factory, middleware, router registration
  config.py              — Pydantic Settings, env var loading
  dependencies.py        — Shared FastAPI dependencies (auth, db, limiter)
  routers/
    auth.py              — JWT verification endpoint
    reports.py           — Report creation, AI trigger, status
    complaints.py        — Complaint CRUD, approval, submission
    rti.py               — RTI eligibility, draft, approve, submit
    admin.py             — Admin status updates, resolution verify
    health.py            — /health endpoint for Render keep-alive
  services/
    report_service.py    — Report workflow orchestration
    complaint_service.py — Complaint workflow orchestration
    rti_service.py       — RTI workflow orchestration
    ai_service.py        — AI pipeline orchestration
    llm_service.py       — LLM + fallback provider
    rag_service.py       — Embedding search + context builder
    authority_service.py — Authority routing from immutable JSON
    storage_service.py   — Supabase Storage signed URL management
    realtime_service.py  — Supabase Realtime publish
  cv/
    pipeline.py          — Master CV orchestrator
    privacy.py           — Face + plate redaction
    detection.py         — YOLOv8n inference
    taxonomy.py          — YOLO class → civic issue category map
    confidence.py        — Evidence confidence scoring
  llm/
    groq_provider.py     — Groq API integration
    watsonx_stub.py      — IBM Watsonx stub (not wired)
    fallback_provider.py — Deterministic template engine
    prompts.py           — Prompt templates
    output_validator.py  — LLM structured output validation
  rag/
    embedder.py          — BAAI embedding with RAM gate
    vector_store.py      — pgvector queries
    chunker.py           — RTI knowledge base chunking
    retriever.py         — Semantic search + keyword fallback
  db/
    supabase_client.py   — Supabase service client
    repositories/
      complaint_repo.py
      report_repo.py
      rti_repo.py
      authority_repo.py  — Reads from static JSON only
  security/
    jwt_verify.py        — JWT RS256 verification
    rbac.py              — Role-based access control
    ownership.py         — IDOR ownership checks
    input_sanitizer.py   — Input validation helpers
  data/
    mangaluru_authorities.json  — IMMUTABLE authority data
```

**Rule:** No business workflow logic may be placed directly inside route handlers. All workflow is in the `services/` layer.

---

## 7. Database Architecture

**Platform:** Supabase PostgreSQL 15, region ap-south-1 (Mumbai)
**Extensions required:** `postgis`, `pgvector`, `uuid-ossp`, `pg_cron` (optional)

**Enums:**
- `complaint_status`: DRAFT → SUBMITTED → UNDER_REVIEW → RESOLVED → REJECTED → ARCHIVED
- `rti_status`: DRAFT → SUBMITTED → ACKNOWLEDGED → RESPONDED → ESCALATED → CLOSED
- `issue_category`: pothole, waterlogging, broken_streetlight, garbage_overflow, open_drain, illegal_construction, water_supply, sewage, road_damage, other
- `user_role`: citizen, admin, authority_officer

**Core tables:**
- `profiles` — extends `auth.users`; fields: id (FK), full_name, phone, role, ward_number, created_at
- `authorities` — seeded from immutable JSON; fields: id, name, jurisdiction, categories[], area_text, contact_email, phone, created_at; **read-only after seed** — no ward geometry, no ward range integers
- `reports` — raw report record before complaint creation; fields: id, user_id (FK), image_original_path, image_redacted_path, image_hash (blake3), location (GEOGRAPHY POINT), address_text, ai_category, ai_confidence, ai_authority_id (FK), ai_raw_response (JSONB), created_at
- `complaints` — approved complaint; fields: id, report_id (FK), user_id (FK), category, description, authority_id (FK), status (enum), submitted_at, resolved_at, resolution_image_path, resolution_notes, mock_gov_ref, created_at, updated_at
- `rti_requests` — RTI linked to stale complaint; fields: id, complaint_id (FK), user_id (FK), status (enum), draft_text, approved_text, mock_submitted_at, rti_ref, created_at, updated_at
- `rti_knowledge_base` — RTI knowledge chunks; fields: id, title, content, embedding (vector(1536)), source_url, created_at
- `audit_log` — immutable append-only audit; fields: id, user_id, action, entity_type, entity_id, metadata (JSONB), ip_address, created_at

**Indexes:**
- `reports.location` — GIST index for PostGIS proximity
- `complaints.user_id`, `complaints.status`, `complaints.authority_id`
- `rti_knowledge_base.embedding` — IVFFlat index for pgvector
- `audit_log.user_id`, `audit_log.entity_id`

**RLS:** Enabled on all tables. Citizens read/write only their own rows. Admins read all. Authority officers read complaints assigned to their authority.

---

## 8. AI/CV Architecture

**RAM strategy (LOCKED — Render free tier = 512 MB):**
- YOLOv8n (~30 MB): loaded on first request, stays resident
- YuNet ONNX (~5 MB): loaded on first request, stays resident
- fast-alpr (~80 MB): loaded on first request, stays resident
- BAAI/bge-large-en-v1.5 (~440 MB): loaded **only if available RAM > 512 MB at load time**; otherwise embedding is disabled and keyword-only RAG is used
- **Models are never all loaded simultaneously** — total resident budget ≤ 115 MB for CV models; embedding model is mutually exclusive with simultaneous CV operation
- All models are lazy-loaded (not at app startup)

**CV pipeline steps (per request):**
1. Receive image bytes from upload endpoint
2. Validate: MIME type, file size (max 10 MB), minimum dimensions
3. Face detection (YuNet) → blur all detected faces
4. Licence plate detection (fast-alpr) → redact all detected plates
5. Save redacted image to Supabase Storage (private bucket)
6. YOLO detection → top predicted civic issue class
7. Map YOLO class to civic issue taxonomy category
8. Compute evidence confidence score (detection confidence × category relevance)
9. Compute blake3 hash of original image for duplicate detection
10. Return: redacted_image_path, category, confidence, hash, bounding_boxes

---

## 9. LLM Architecture

**Provider chain (LOCKED):**
1. Groq API — `llama-3.1-8b-instant` — primary provider
2. Deterministic template engine — fallback when Groq is unavailable or rate-limited
3. IBM Watsonx stub — provider interface exists but is NOT wired; future use only

**LLM responsibilities:**
- Generate complaint description from CV results + location + category
- Draft RTI letter from complaint context + RAG context
- Classify ambiguous categories when YOLO confidence < 0.5

**Prompt injection protection:**
- All citizen-supplied text is sanitized before injection into prompts
- LLM output is validated against a Pydantic schema before use
- Any LLM response failing schema validation falls back to deterministic template

**Output contract (Pydantic schema):**
- `category: IssueCategory`
- `description: str` (max 500 chars)
- `authority_recommendation: str` (authority name, must match authority JSON)
- `confidence: float` (0.0–1.0)

---

## 10. RAG Architecture

**Purpose:** Provide RTI-relevant legal/procedural context to the LLM when drafting RTI letters.

**Knowledge base:** RTI Act provisions, Mangaluru MCC complaint procedures, Karnataka civic law — chunked and embedded.

**Pipeline:**
1. RTI knowledge base documents are chunked (max 512 tokens per chunk)
2. Each chunk is embedded using BAAI/bge-large-en-v1.5 → stored in `rti_knowledge_base.embedding` (pgvector)
3. At RTI draft time: embed the complaint description → pgvector similarity search → retrieve top-5 chunks
4. If embedding model unavailable (RAM constraint): keyword-based fallback search on `rti_knowledge_base.content`
5. Retrieved chunks injected as context into RTI draft prompt

---

## 11. Mapping/Geospatial Architecture

**Library:** MapLibre GL JS 4.x (frontend), PostGIS (backend)
**Tiles:** OpenFreeMap (openfreemap.org) — free, no API key
**GPS:** Browser Geolocation API → GEOGRAPHY POINT stored in `reports.location`
**Fallback:** If GPS unavailable → citizen manually pins location on MapLibre map
**Duplicate detection:** PostGIS ST_DWithin query — flag complaints within 50m of same category as potential duplicates

---

## 12. Mangaluru Authority-Routing Architecture

**Source of truth:** `backend/data/mangaluru_authorities.json` — IMMUTABLE

**MVP Routing rule (LOCKED — ADR-001):**
Authority routing uses `issue_type` (complaint category) and `area_text` (free-text area/location description).
No ward polygons, no GeoJSON geometries, no PostGIS polygon containment, and no ward number range mapping
are required or permitted for MVP authority routing.
PostGIS remains enabled for duplicate-detection proximity queries on `reports.location` only.

**Routing logic:**
1. Extract complaint category from AI pipeline
2. Extract `address_text` from report (free-text location description)
3. Query authority JSON: match `categories` array → find authorities supporting this issue_type
4. If multiple authorities match → select by `area_text` keyword match against authority `area_text` field
5. If no text match → assign category default authority (first match in JSON for that category)
6. Citizen may override AI authority recommendation before submission

**Authorities data structure:**
```json
{
  "authorities": [
    {
      "id": "uuid",
      "name": "Mangaluru City Corporation",
      "categories": ["pothole", "road_damage", "garbage_overflow"],
      "area_text": "Mangaluru city limits",
      "contact_email": "...",
      "phone": "..."
    }
  ]
}
```

---

## 13. Security Architecture

**Authentication:** Supabase Auth JWT (RS256). Backend verifies JWT on every request.
**Authorization:** RBAC via `profiles.role`. Three roles: citizen, admin, authority_officer.
**IDOR protection:** Every data query includes `user_id = current_user.id` filter; admins bypass via explicit admin check.
**Input validation:** Pydantic schemas on all API request bodies; Zod on all frontend forms.
**Rate limiting:** slowapi on FastAPI — 10 req/min for AI endpoints, 60 req/min for standard endpoints.
**Upload security:** MIME type check + magic bytes check; max 10 MB; reject non-image MIME types.
**Prompt injection:** Sanitize all user text before LLM prompt injection; validate all LLM outputs.
**SQL injection:** Supabase client uses parameterized queries; no raw SQL string interpolation.
**XSS:** Next.js escapes JSX; API returns JSON only; no HTML rendering of user content.
**CORS:** FastAPI CORS restricted to Vercel frontend domain + localhost in dev.
**Secrets:** All secrets in environment variables; never committed to source; Render env vars for backend, Vercel env vars for frontend.
**Storage:** All images in private Supabase Storage buckets; accessed only via signed URLs (15-min expiry).
**Audit log:** Every state-changing action recorded in `audit_log` (immutable).
**Mock government:** No real government API is ever called. Mock submission generates a fake reference number only.

---

## 14. Privacy Architecture

**Face redaction:** YuNet detects all faces → Pillow applies Gaussian blur before storage
**Plate redaction:** fast-alpr detects licence plates → Pillow applies black rectangle before storage
**Storage rule:** Original (un-redacted) image is stored in a separate private bucket, accessible only to the submitting citizen and admins; redacted image is the public-facing record
**Data minimization:** Phone number optional; no tracking; no analytics; no third-party SDKs
**Location:** GPS coordinates stored only for the specific complaint; not tracked over time

---

## 15. Complaint Lifecycle

```
Citizen takes photo (camera only)
  → Backend: CV pipeline (face+plate redaction, YOLO detection, hash)
  → Backend: LLM generates description + authority recommendation
  → Frontend: Citizen reviews AI result, edits if needed
  → Frontend: Citizen approves and submits
  → Database: Complaint created with status=SUBMITTED
  → Backend: Mock government submission → mock_gov_ref generated
  → Supabase Realtime: Status update pushed to frontend
  → [30 days pass with no RESOLVED status]
  → Frontend: RTI button becomes available
  → RTI flow begins
```

**Status progression:** DRAFT → SUBMITTED → UNDER_REVIEW → RESOLVED | REJECTED | ARCHIVED

---

## 16. RTI Lifecycle

```
Complaint age ≥ 30 days AND status ≠ RESOLVED
  → Frontend: RTI button visible
  → Citizen clicks → Backend: RTI eligibility check
  → Backend: RAG retrieval (pgvector or keyword fallback)
  → Backend: LLM drafts RTI letter
  → Frontend: Citizen reviews and edits RTI draft
  → Frontend: Citizen approves RTI
  → Backend: Mock RTI submission → rti_ref generated
  → Database: rti_status = SUBMITTED
```

**RTI status progression:** DRAFT → SUBMITTED → ACKNOWLEDGED → RESPONDED → ESCALATED → CLOSED

---

## 17. Offline/PWA Architecture

**MVP offline scope (LOCKED):**
- App shell is cached by service worker (offline access to UI chrome)
- Draft complaint data (form fields + image blob) stored in IndexedDB as `DRAFT_OFFLINE`
- When offline: citizen can fill report form; AI analysis requires connectivity (deferred)
- On reconnect: citizen sees "pending drafts" list and manually taps "Retry" to submit
- **No background sync** — no automatic retry without explicit citizen action
- API calls are network-first; no API response caching for offline fallback

**Out of scope:** Background Sync API, Push Notifications, periodic background fetch.

---

## 18. API Architecture

**Base URL:** `https://civicai-backend.onrender.com/api/v1`

**Endpoints (summary):**
```
POST   /reports/                        — Create report (upload image, trigger AI)
GET    /reports/{id}                    — Get report with AI results
POST   /complaints/                     — Create complaint from approved report
GET    /complaints/                     — List user's complaints
GET    /complaints/{id}                 — Get complaint detail
PATCH  /complaints/{id}/status          — Admin: update status
POST   /complaints/{id}/submit          — Citizen: final approval + mock gov submit
POST   /complaints/{id}/resolve         — Admin: mark resolved + upload resolution photo
POST   /rti/                            — Create RTI draft for eligible complaint
GET    /rti/{id}                        — Get RTI draft
POST   /rti/{id}/approve                — Citizen: approve and mock-submit RTI
GET    /admin/complaints                — Admin: all complaints
GET    /health                          — Health check
```

**Contract rules:**
- All requests authenticated via `Authorization: Bearer <jwt>` header
- All responses in `{"data": ..., "error": null}` envelope
- All errors in `{"data": null, "error": {"code": "...", "message": "..."}}`
- No endpoint returns raw database rows; all responses go through service/schema layer

---

## 19. Authentication and Authorization

**Auth provider:** Supabase Auth (email/password + optional OTP)
**JWT:** RS256, verified on every FastAPI request via `dependencies.py`
**Session:** Supabase client manages token refresh on frontend
**RBAC roles:**
- `citizen` — create/read own reports, complaints, RTIs
- `admin` — read all, update complaint status, mark resolved
- `authority_officer` — read complaints assigned to their authority only
**IDOR:** All service layer queries filter by `user_id`; admin queries use explicit `is_admin` flag

---

## 20. Storage Architecture

**Buckets (Supabase Storage):**
- `report-originals` — private; original un-redacted images; RLS: owner + admin only
- `report-redacted` — private; redacted images; RLS: owner + admin + authority_officer for assigned complaints
- `resolution-photos` — private; admin-uploaded resolution evidence; RLS: owner read, admin write
- `rti-documents` — private; RTI draft documents; RLS: owner only

**Access pattern:** All image access via signed URLs (15-min expiry). Backend generates signed URLs; frontend never accesses storage directly.

**RLS policies:** Supabase Storage RLS mirrors database RLS. No bucket is public.

---

## 21. Database / ER Design

```
auth.users (Supabase managed)
    ↑ 1:1
profiles (id FK → auth.users.id, full_name, phone, role, ward_number)

reports (id, user_id FK→profiles, image_original_path, image_redacted_path,
         image_hash, location GEOGRAPHY, address_text, ai_category,
         ai_confidence, ai_authority_id FK→authorities, ai_raw_response JSONB)
    ↑ 1:1
complaints (id, report_id FK→reports, user_id FK→profiles, category,
            description, authority_id FK→authorities, status, submitted_at,
            resolved_at, resolution_image_path, mock_gov_ref)
    ↑ 1:1
rti_requests (id, complaint_id FK→complaints, user_id FK→profiles,
              status, draft_text, approved_text, mock_submitted_at, rti_ref)

authorities (id, name, jurisdiction, categories[], area_text, contact_email, phone)
  [SEEDED FROM IMMUTABLE JSON — no application writes; no ward geometry; no ward range]

rti_knowledge_base (id, title, content, embedding vector(1536), source_url)

audit_log (id, user_id, action, entity_type, entity_id, metadata JSONB,
           ip_address, created_at)
  [APPEND-ONLY — no updates or deletes permitted]
```

---

## 22. Data Flow

```
1. Image Upload
   Citizen → Next.js → FastAPI /reports/ → CV Pipeline → Supabase Storage
                                         → YOLO + LLM → Supabase DB (reports)

2. Complaint Approval
   Citizen reviews AI results → Citizen approves → FastAPI /complaints/
   → Supabase DB (complaints, status=SUBMITTED) → Mock Gov API (fake ref)
   → Supabase Realtime → Frontend status update

3. RTI Flow
   Frontend RTI trigger → FastAPI /rti/ → Eligibility check
   → RAG (pgvector) → LLM draft → DB (rti_requests, status=DRAFT)
   → Citizen edits → Citizen approves → Mock RTI submit → DB update
```

---

## 23. AI Flow

```
Image bytes received
  │
  ├── Validate (MIME, size, dimensions)
  ├── YuNet: detect faces → blur
  ├── fast-alpr: detect plates → redact
  ├── Store redacted image → Supabase Storage
  ├── blake3 hash → duplicate check (ST_DWithin + hash match)
  ├── YOLOv8n: detect objects → top class
  ├── Taxonomy map: YOLO class → civic category
  ├── Confidence score: detection confidence × category relevance weight
  ├── Authority router: category + location → authority recommendation
  └── LLM:
        ├── Groq (primary): structured prompt → Pydantic validated output
        └── Fallback: deterministic template if Groq fails or output invalid
```

---

## 24. Complaint State Machine

```
States: DRAFT, SUBMITTED, UNDER_REVIEW, RESOLVED, REJECTED, ARCHIVED

Transitions:
  DRAFT        → SUBMITTED     (trigger: citizen approval via /complaints/{id}/submit)
  SUBMITTED    → UNDER_REVIEW  (trigger: admin action via /complaints/{id}/status)
  UNDER_REVIEW → RESOLVED      (trigger: admin via /complaints/{id}/resolve + photo)
  UNDER_REVIEW → REJECTED      (trigger: admin via /complaints/{id}/status)
  RESOLVED     → ARCHIVED      (trigger: system, 90 days after resolution)
  REJECTED     → ARCHIVED      (trigger: system, 30 days after rejection)

Side effects:
  SUBMITTED:    mock_gov_ref generated; Realtime event published
  RESOLVED:     resolution_image_path stored; Realtime event published; RTI blocked
  REJECTED:     Realtime event published
  ARCHIVED:     no Realtime event; read-only

RTI eligibility gate:
  complaint.status == UNDER_REVIEW OR SUBMITTED
  AND (NOW() - complaint.submitted_at) >= 30 days
  AND no existing rti_request for this complaint
```

---

## 25. RTI State Machine

```
States: DRAFT, SUBMITTED, ACKNOWLEDGED, RESPONDED, ESCALATED, CLOSED

Transitions:
  DRAFT        → SUBMITTED     (trigger: citizen approval via /rti/{id}/approve)
  SUBMITTED    → ACKNOWLEDGED  (trigger: mock only — automatic after submission)
  ACKNOWLEDGED → RESPONDED     (trigger: admin demo action)
  ACKNOWLEDGED → ESCALATED     (trigger: admin demo action — 30 days no response)
  RESPONDED    → CLOSED        (trigger: admin demo action)
  ESCALATED    → CLOSED        (trigger: admin demo action)

Note: All RTI authority interactions are mock. No real government API is called.
```

---

## 26. Deployment Architecture

**Frontend (Vercel):**
- Repo: `/frontend` directory
- Auto-deploy on push to `main`
- Environment: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL`

**Backend (Render free web service):**
- Repo: `/backend` directory
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `ALLOWED_ORIGINS`
- Keep-alive: cron-job.org pings `/health` every 14 minutes (Render free tier sleeps at 15 min)
- RAM: 512 MB hard limit — AI models must respect this

**Database (Supabase free tier):**
- Region: ap-south-1 (Mumbai)
- 500 MB database storage limit
- 1 GB file storage limit

**CI/CD (GitHub Actions):**
- On PR: lint + typecheck + unit tests
- On merge to main: deploy frontend to Vercel, deploy backend to Render

---

## 27. Testing Strategy

**Backend:**
- pytest unit tests for all services and CV pipeline
- pytest-asyncio for async FastAPI route tests
- Supabase test schema for DB integration tests
- RLS policy tests using service role vs citizen JWT

**Frontend:**
- Jest + React Testing Library for components
- Playwright E2E for critical flows: report creation, complaint approval, RTI flow

**AI/CV:**
- Test images with known faces/plates for redaction verification
- Known civic issue images for YOLO category accuracy
- LLM schema validation tests with mocked Groq responses
- Prompt injection tests

**Security:**
- IDOR test: citizen A cannot access citizen B's complaints
- RLS test: raw SQL insert bypassing API must fail for wrong user
- Upload: malformed MIME, oversized file, non-image must be rejected

---

## 28. Threat Model

| Threat | Mitigation |
|--------|-----------|
| JWT forgery | RS256 verification; Supabase managed key rotation |
| IDOR | All queries filter by user_id; explicit ownership checks |
| SQL injection | Parameterized queries via Supabase client |
| XSS | JSX escaping; JSON-only API responses |
| Malicious image upload | MIME + magic bytes check; Pillow re-encode; max 10 MB |
| Prompt injection | Input sanitization; LLM output schema validation |
| Path traversal | Storage paths are UUIDs only; no user-controlled path components |
| Abuse / scraping | Rate limiting via slowapi; Supabase Auth brute-force protection |
| Secret leakage | Env vars only; no hardcoded secrets; `.env` in `.gitignore` |
| Mock gov bypass | Mock submission is enforced at service layer; no real endpoint exists |

---

## 29. Performance Strategy

**Backend (Render 512 MB RAM):**
- Lazy AI model loading — models loaded on first request, not startup
- BAAI embedding model disabled if available RAM < 512 MB at load time
- YOLOv8n + YuNet + fast-alpr total ≈ 115 MB resident after first load
- Image resized to max 1024px before CV inference to reduce memory pressure
- LLM calls are async (httpx); do not block ASGI event loop

**Frontend:**
- Next.js image optimization for all UI images
- SWR stale-while-revalidate for complaint lists
- MapLibre tiles cached by browser
- PWA app shell cached by service worker

**Database:**
- GiST index on `reports.location` for fast proximity queries
- IVFFlat index on `rti_knowledge_base.embedding` for fast vector search
- Composite index on `complaints(user_id, status)` for dashboard queries

---

## 30. Free-Tier / Cost Analysis

| Service | Free Limit | Expected Usage | Buffer |
|---------|-----------|----------------|--------|
| Vercel Hobby | 100 GB bandwidth/mo | <1 GB | ✓ |
| Render free | 750 hrs/mo, 512 MB RAM | <100 hrs demo | ✓ |
| Supabase free | 500 MB DB, 1 GB storage | <50 MB demo | ✓ |
| Groq API | ~14,400 req/day free | <100 req demo | ✓ |
| GitHub Actions | 2,000 min/mo | <100 min | ✓ |
| cron-job.org | unlimited | 1 job | ✓ |
| OpenFreeMap | unlimited | tiles only | ✓ |

**Total cost: ₹0 / $0**

---

## 31. Five-Member Team Division

| Member | Role | Primary Responsibilities |
|--------|------|------------------------|
| M1 | Frontend / UX | Next.js pages, components, PWA, MapLibre, offline flow |
| M2 | Backend / API | FastAPI routes, services, authority routing, mock gov |
| M3 | AI / CV / LLM | CV pipeline, YOLO, face/plate redaction, LLM, RAG |
| M4 | Database / Security | Supabase schema, RLS, migrations, auth, audit log |
| M5 | DevOps / QA | CI/CD, Render deploy, Vercel deploy, tests, keep-alive |

---

## 32. Hackathon Demo Flow

1. M5 confirms all services are live (Render, Vercel, Supabase)
2. Open PWA on mobile browser
3. Login as demo citizen
4. Tap "Report Issue" → Camera opens
5. Photograph a pothole (test image)
6. AI pipeline runs: redaction → YOLO → LLM → authority recommendation shown
7. Citizen reviews: AI says "Pothole - MCC Roads Department"
8. Citizen approves → Complaint SUBMITTED → mock_gov_ref shown
9. Admin login → Update status to UNDER_REVIEW → Realtime update visible on citizen screen
10. Fast-forward 30 days (set complaint date to 30 days ago in demo DB)
11. RTI button appears → Citizen taps → AI drafts RTI letter
12. Citizen approves → RTI SUBMITTED → mock rti_ref shown
13. Show offline demo: disable WiFi → fill report → save as DRAFT_OFFLINE → re-enable WiFi → manual retry

---

## 33. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Render cold start (30s) | High | Medium | cron-job.org keep-alive every 14 min |
| Groq rate limit during demo | Medium | High | Deterministic fallback always ready |
| BAAI model OOM on Render | High | Low | RAM gate disables embedding; keyword RAG fallback |
| Supabase free tier storage full | Low | Medium | Compress images; monitor during dev |
| MapLibre tiles unavailable | Low | Medium | OpenFreeMap CDN is reliable; cached tiles |
| YOLOv8n low accuracy on demo image | Medium | Medium | Allow citizen to override AI category |

---

## 34. Explicit Out-of-Scope Features

- Real government API integration (all submission is mock-only)
- Push notifications
- Background Sync API
- SMS/WhatsApp notifications
- Gallery photo upload (camera-first only in main flow)
- Multi-language / i18n (English only for hackathon)
- Payments or fees
- Social features (upvotes, comments)
- Public complaint map (complaints are private to submitter + admin)
- Third-party analytics (no GA, no Mixpanel)
- Native mobile app (PWA only)
- IBM Watsonx integration (stub only — not wired)

---

## 35. Changes from Previous Architecture

- MapLibre replaces Leaflet (no API key, better vector tile support)
- OpenFreeMap replaces OpenStreetMap direct tile usage
- serwist replaces legacy next-pwa
- fast-alpr replaces custom ALPR script
- YuNet ONNX replaces MediaPipe face detection (lighter dependency)
- Groq API replaces OpenAI (free tier available)
- Render replaces Railway for backend hosting

---

## 36. Final Project / Module Structure

```
civicai/
  frontend/                    (Next.js 14)
    app/
    components/
    lib/
    public/
    next.config.js
    package.json
  backend/                     (FastAPI)
    main.py
    config.py
    dependencies.py
    routers/
    services/
    cv/
    llm/
    rag/
    db/
    security/
    data/
      mangaluru_authorities.json
    requirements.txt
  supabase/
    migrations/
    seed/
  .github/
    workflows/
  docs/
    CIVICAI_MASTER_ARCHITECTURE.md
    CIVICAI_MASTER_ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md
```

---

## 37. Final Approval Checklist

- [x] Zero-cost architecture confirmed
- [x] All services verified free at hackathon scale
- [x] Mangaluru jurisdiction confirmed
- [x] Camera-first workflow locked
- [x] AI-assist / citizen-decides principle locked
- [x] Mock-government-only submission locked
- [x] Privacy redaction before storage locked
- [x] RAM strategy for Render 512 MB locked
- [x] Complaint state machine approved
- [x] RTI state machine approved
- [x] MVP offline scope locked (no background sync)
- [x] Security architecture approved
- [x] RLS on all tables approved
- [x] Immutable authority data approved
- [x] Five-member team division approved

---

## 38. Fixed Requirements

1. Camera capture is the primary input method; no gallery upload in main flow
2. AI analysis is mandatory before complaint creation
3. Citizen must explicitly approve all AI recommendations before submission
4. No complaint or RTI is ever submitted without citizen approval
5. All government submission is mock — no real government API
6. Face and licence plate redaction must occur before any image is stored in accessible storage
7. Authority data is loaded from immutable JSON — never modified by application logic
8. RTI is available only when complaint age ≥ 30 days AND status ≠ RESOLVED
9. All data access enforces RLS — no bypass permitted
10. Backend RAM budget is 512 MB — all AI model loading must respect this

---

## 39. Technical Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend framework | Next.js 14 App Router | SSR, Vercel native, TypeScript |
| Backend framework | FastAPI | Async, Pydantic, Python AI ecosystem |
| Database | Supabase PostgreSQL | Free, Auth+Storage+Realtime bundled |
| LLM | Groq llama-3.1-8b-instant | Free tier, fast inference |
| Object detection | YOLOv8n | Lightest YOLO, CPU-only |
| Face detection | YuNet ONNX | 5 MB, OpenCV compatible |
| Plate detection | fast-alpr | Self-contained, CPU-only |
| Embedding | BAAI/bge-large-en-v1.5 | Best free model; RAM-gated |
| Map tiles | OpenFreeMap | Free, no key, reliable |
| Offline | IndexedDB manual retry | MVP-safe, no background sync |
| Image hash | blake3 | Fast, collision-resistant |
| **ADR-001: Authority routing method** | **issue_type + area_text keyword match** | **No ward geometry available for MVP; PostGIS not required for routing; simpler and sufficient for hackathon scale** |

---

## 40. Unresolved Decisions Requiring Approval

> As of architecture lock v2.0, the following items are deferred to the implementation phase but require explicit decision before coding begins:

1. ~~**Ward boundary data format**~~ — **RESOLVED (ADR-001).** Authority routing uses `issue_type` (complaint category) and `area_text` (free-text field in authorities JSON). No ward polygons, no GeoJSON geometries, no PostGIS polygon containment, and no ward number range mapping. PostGIS remains for `reports.location` duplicate detection only. The `authorities` table stores `area_text TEXT` instead of any geometry or ward range fields.
2. **Admin account provisioning** — How are admin users created? (Manual Supabase dashboard role assignment is assumed; automated admin creation is out of scope.)
3. **Demo date manipulation** — For the hackathon demo, how is the 30-day RTI trigger simulated? (Agreed approach: set `submitted_at` to 31 days ago in seed data.)
4. **Resolution photo bucket** — Confirm `resolution-photos` is a separate bucket from `report-redacted`. (Assumed: yes, separate bucket.)

---

> **END OF PART A — MASTER ARCHITECTURE**
> All decisions above are LOCKED. Modifications require an ADR.

---

# PART B — EXECUTION-READY IMPLEMENTATION PLAN

> Derived strictly from the LOCKED Master Architecture (Part A).
> No architectural decisions are made here. All technology, workflow,
> and scope choices reference Part A sections explicitly.
> Implementation agents must not redesign any decision listed in Part A.

---

## Responsibility Matrix

| Member | Role | Domain |
|--------|------|--------|
| M1 | Frontend / UX | Next.js, TypeScript, Tailwind, shadcn/ui, MapLibre, PWA, IndexedDB |
| M2 | Backend / API | FastAPI, Python, services layer, authority routing, mock gov submission |
| M3 | AI / CV / LLM | YOLOv8n, YuNet, fast-alpr, BAAI embeddings, Groq, RAG, LLM fallback |
| M4 | Database / Security | Supabase, PostgreSQL, PostGIS, pgvector, RLS, migrations, audit log |
| M5 | DevOps / QA | GitHub Actions, Render, Vercel, cron-job.org, CI/CD, test runner |

---

## Phase Overview

| Phase | Name | Blocking |
|-------|------|---------|
| 0 | Foundation / Validation | YES — all other phases blocked until complete |
| 1 | Database / Auth | YES — Backend, AI, Frontend blocked until complete |
| 2 | AI / CV / LLM | Parallel with Phase 3 after Phase 1 |
| 3 | Backend / API Services | Parallel with Phase 2 after Phase 1 |
| 4 | Frontend / PWA | Requires Phase 1+2+3 complete |
| 5 | Security / Integration | Requires Phase 1+2+3+4 complete |
| 6 | Deployment / Demo | Requires Phase 5 complete |

---

## Phase 0 — Foundation / Validation

### Objective
Establish the repository structure, tooling, environment configuration, and
dependency validation before any feature work begins. Every subsequent phase
depends on Phase 0 completion.

### Entry Criteria
- GitHub repository created
- All five team members have repository access

### Phase 0 Tasks

---

#### T0-1: Repository scaffolding
- **Phase:** 0
- **Owner:** M5 (primary), M1 + M2 (support)
- **Objective:** Create the monorepo directory structure as defined in Part A §36.
- **Scope:**
  - Create `/frontend`, `/backend`, `/supabase/migrations`, `/supabase/seed`, `/.github/workflows`, `/docs` directories
  - Add root `.gitignore` (node_modules, __pycache__, .env, .env.local, *.pyc, .DS_Store)
  - Add root `README.md` with project overview
- **Non-goals:** Do not install any dependencies yet. Do not create application code.
- **Expected files:** `README.md`, `.gitignore`, directory structure
- **Dependencies:** None
- **Prerequisite tasks:** None
- **Complexity:** S
- **Blocking:** YES — T0-2 through T0-5 cannot start until structure exists
- **Parallelizable:** NO
- **Handoff:** M5 → all members: repo URL + branch strategy confirmed
- **Acceptance criteria:**
  - Repository is accessible to all team members
  - Directory structure matches Part A §36 exactly
  - `.gitignore` covers all local environment files
- **Required tests:** Manual verification only

---

#### T0-2: Frontend project bootstrap
- **Phase:** 0
- **Owner:** M1 (primary), M5 (support)
- **Objective:** Initialize Next.js 14 App Router project with TypeScript, Tailwind CSS, shadcn/ui.
- **Scope:**
  - `npx create-next-app@14` with TypeScript + Tailwind + App Router
  - Install and configure shadcn/ui (init)
  - Add `next.config.js` skeleton
  - Configure `tsconfig.json` path aliases (`@/` → `./src/`)
  - Add `.env.local.example` with required frontend env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL`
- **Non-goals:** Do not implement any pages. Do not configure PWA yet. Do not add MapLibre yet.
- **Expected files:** `frontend/package.json`, `frontend/next.config.js`, `frontend/tsconfig.json`, `frontend/app/layout.tsx`, `frontend/.env.local.example`
- **LOCKED decisions:** Next.js 14, TypeScript 5.x, Tailwind 3.x, shadcn/ui (Part A §2)
- **Dependencies:** T0-1
- **Prerequisite tasks:** T0-1
- **Complexity:** S
- **Blocking:** YES — all frontend tasks blocked until bootstrap complete
- **Parallelizable:** Parallel with T0-3 after T0-1
- **Handoff:** M1 → all: `npm run dev` confirmed working at localhost:3000
- **Acceptance criteria:**
  - `npm run dev` starts without errors
  - TypeScript compilation passes with `npm run build`
  - Tailwind CSS classes render correctly on default page
- **Required tests:** `npm run build` must pass

---

#### T0-3: Backend project bootstrap
- **Phase:** 0
- **Owner:** M2 (primary), M5 (support)
- **Objective:** Initialize FastAPI project with Python 3.11, create requirements.txt, configure Pydantic Settings.
- **Scope:**
  - Create `backend/requirements.txt` with pinned dependencies: fastapi==0.111.*, uvicorn, slowapi, httpx, pillow, blake3, python-multipart, pydantic-settings, supabase, python-jose[cryptography]
  - Create `backend/main.py` — app factory skeleton (no routes yet, just health endpoint)
  - Create `backend/config.py` — Pydantic Settings class with all env vars
  - Create `backend/.env.example` with: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `ALLOWED_ORIGINS`, `ENV`
  - Create `backend/routers/health.py` — GET /health → 200 OK
- **Non-goals:** Do not implement any business logic. Do not configure AI dependencies yet.
- **Expected files:** `backend/requirements.txt`, `backend/main.py`, `backend/config.py`, `backend/routers/health.py`, `backend/.env.example`
- **LOCKED decisions:** FastAPI 0.111.x, Python 3.11, slowapi, httpx, Pillow, blake3 (Part A §2, §6)
- **Dependencies:** T0-1
- **Prerequisite tasks:** T0-1
- **Complexity:** S
- **Blocking:** YES — all backend tasks blocked until bootstrap complete
- **Parallelizable:** Parallel with T0-2 after T0-1
- **Handoff:** M2 → all: `uvicorn main:app --reload` confirmed running; `/health` returns 200
- **Acceptance criteria:**
  - `uvicorn main:app --reload` starts without errors
  - `GET /health` returns `{"status": "ok"}`
  - Pydantic Settings loads from `.env` without errors
- **Required tests:** `pytest` — 1 test: `GET /health` → 200

---

#### T0-4: Supabase project initialization
- **Phase:** 0
- **Owner:** M4 (primary), M5 (support)
- **Objective:** Create Supabase project in ap-south-1, confirm extensions, retrieve credentials.
- **Scope:**
  - Create Supabase project (region: ap-south-1 / Mumbai)
  - Enable extensions: `postgis`, `pgvector`, `uuid-ossp`
  - Record and distribute (via secure channel): `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
  - Confirm free-tier limits are acceptable (Part A §30)
- **Non-goals:** Do not create any tables yet. Do not configure RLS yet.
- **Expected output:** Supabase project URL + keys distributed to M1, M2, M4
- **LOCKED decisions:** Supabase ap-south-1, PostgreSQL 15, PostGIS, pgvector (Part A §2, §7)
- **Dependencies:** T0-1
- **Prerequisite tasks:** T0-1
- **Complexity:** S
- **Blocking:** YES — T1 database tasks blocked until project exists
- **Parallelizable:** Parallel with T0-2, T0-3
- **Handoff:** M4 → M1, M2, M5: `.env` values confirmed; Supabase dashboard accessible
- **Acceptance criteria:**
  - Supabase dashboard accessible
  - `SELECT postgis_version();` returns result in Supabase SQL editor
  - `SELECT * FROM pg_extension WHERE extname = 'vector';` returns result
- **Required tests:** Manual SQL verification in Supabase dashboard

---

#### T0-5: CI/CD pipeline setup
- **Phase:** 0
- **Owner:** M5 (primary)
- **Objective:** Create GitHub Actions workflows for lint, typecheck, unit tests on PR; deploy on merge to main.
- **Scope:**
  - `.github/workflows/ci.yml` — on PR: frontend typecheck + lint, backend pytest
  - `.github/workflows/deploy.yml` — on push to main: trigger Vercel + Render deploy hooks
  - Configure GitHub repository secrets: `VERCEL_TOKEN`, `RENDER_DEPLOY_HOOK_URL`
- **Non-goals:** Do not configure Vercel or Render projects yet (that is Phase 6). Do not add integration tests yet.
- **Expected files:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
- **LOCKED decisions:** GitHub Actions, Vercel, Render (Part A §26)
- **Dependencies:** T0-2, T0-3
- **Prerequisite tasks:** T0-2, T0-3
- **Complexity:** S
- **Blocking:** NO — development can proceed without CI; CI should be in place before Phase 5
- **Parallelizable:** YES — parallel with Phase 1 work
- **Handoff:** M5 → all: CI badge green on main branch
- **Acceptance criteria:**
  - PR CI runs lint + typecheck + pytest without failures
  - Green CI badge on README
- **Required tests:** CI itself is the test

---

### Phase 0 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T0-1: Repository structure matches Part A §36
- [ ] T0-2: `npm run build` passes
- [ ] T0-3: `GET /health` returns 200
- [ ] T0-4: Supabase project live with PostGIS + pgvector extensions enabled
- [ ] T0-5: CI pipeline passes on main branch

**NO-GO if:** Any of the above fails. Do not proceed to Phase 1 until all Phase 0 gates pass.

### Phase 0 Deliverables
- Confirmed repository structure
- Working Next.js skeleton
- Working FastAPI skeleton
- Supabase project with extensions
- CI/CD pipeline active

---

## Phase 1 — Database / Auth

### Objective
Implement the complete Supabase database schema, RLS policies, storage buckets,
seed data, and authentication flow. All downstream phases depend on this schema.

### Entry Criteria
- Phase 0 all gates passed
- Supabase project live (T0-4 complete)

### Phase 1 Tasks

---

#### T1-1: Database enums and extensions
- **Phase:** 1
- **Owner:** M4 (primary)
- **Objective:** Create all PostgreSQL enums and confirm extensions are active.
- **Scope:**
  - Migration file: `supabase/migrations/001_enums.sql`
  - Create enum `complaint_status`: DRAFT, SUBMITTED, UNDER_REVIEW, RESOLVED, REJECTED, ARCHIVED
  - Create enum `rti_status`: DRAFT, SUBMITTED, ACKNOWLEDGED, RESPONDED, ESCALATED, CLOSED
  - Create enum `issue_category`: pothole, waterlogging, broken_streetlight, garbage_overflow, open_drain, illegal_construction, water_supply, sewage, road_damage, other
  - Create enum `user_role`: citizen, admin, authority_officer
- **Non-goals:** Do not create tables yet.
- **LOCKED decisions:** All enum values from Part A §7
- **Dependencies:** T0-4
- **Prerequisite tasks:** T0-4
- **Complexity:** S
- **Blocking:** YES — all table creation tasks depend on these enums
- **Parallelizable:** NO
- **Handoff:** M4 → M2, M3: enum SQL applied; share migration file
- **Acceptance criteria:** All four enums exist in Supabase; `SELECT enum_range(NULL::complaint_status)` returns correct values
- **Required tests:** SQL verification in Supabase dashboard

---

#### T1-2: Core table creation
- **Phase:** 1
- **Owner:** M4 (primary)
- **Objective:** Create all core application tables as defined in Part A §21.
- **Scope:**
  - Migration: `supabase/migrations/002_tables.sql`
  - Tables: `profiles`, `authorities`, `reports`, `complaints`, `rti_requests`, `rti_knowledge_base`, `audit_log`
  - All columns, types, constraints, FK relationships as per Part A §21
  - `rti_knowledge_base.embedding` — `vector(1536)` column (pgvector)
  - `reports.location` — `GEOGRAPHY(POINT, 4326)` column (PostGIS)
  - `audit_log` — include `CHECK` constraint preventing UPDATE/DELETE
- **Non-goals:** Do not create indexes yet (T1-3). Do not configure RLS yet (T1-4).
- **LOCKED decisions:** Part A §7, §21
- **Dependencies:** T1-1
- **Prerequisite tasks:** T1-1
- **Complexity:** M
- **Blocking:** YES — RLS, indexes, seed, API depend on tables existing
- **Parallelizable:** NO
- **Handoff:** M4 → all: migration applied; table structure confirmed
- **Acceptance criteria:** All 7 tables exist; FK constraints enforced; `\d+ complaints` shows all columns
- **Required tests:** Insert test row into each table; FK violation test

---

#### T1-3: Database indexes
- **Phase:** 1
- **Owner:** M4 (primary)
- **Objective:** Create all performance indexes as defined in Part A §7.
- **Scope:**
  - Migration: `supabase/migrations/003_indexes.sql`
  - GiST index on `reports.location`
  - IVFFlat index on `rti_knowledge_base.embedding` (lists=100)
  - Composite index on `complaints(user_id, status)`
  - Indexes on `complaints.authority_id`, `audit_log.user_id`, `audit_log.entity_id`
- **LOCKED decisions:** Part A §7, §29
- **Dependencies:** T1-2
- **Prerequisite tasks:** T1-2
- **Complexity:** S
- **Blocking:** NO — application works without indexes but performance degrades
- **Parallelizable:** Parallel with T1-4 after T1-2
- **Handoff:** M4 → M2: indexes confirmed; share EXPLAIN ANALYZE baseline
- **Acceptance criteria:** `\di` shows all indexes; EXPLAIN ANALYZE on location query uses GiST index
- **Required tests:** EXPLAIN ANALYZE confirms index usage

---

#### T1-4: Row Level Security (RLS) policies
- **Phase:** 1
- **Owner:** M4 (primary)
- **Objective:** Enable RLS on all tables and implement access policies per Part A §7, §19, §20.
- **Scope:**
  - Migration: `supabase/migrations/004_rls.sql`
  - Enable RLS on: profiles, reports, complaints, rti_requests, rti_knowledge_base, audit_log
  - `profiles`: SELECT own row; INSERT own row on registration; no UPDATE role field via API
  - `reports`: citizen SELECT/INSERT own; admin SELECT all
  - `complaints`: citizen SELECT/INSERT own; admin SELECT/UPDATE all; authority_officer SELECT where authority_id matches
  - `rti_requests`: citizen SELECT/INSERT own; admin SELECT all
  - `rti_knowledge_base`: SELECT all (read-only for all authenticated); INSERT via service role only
  - `audit_log`: INSERT via service role only; SELECT own rows for citizen; SELECT all for admin
- **Non-goals:** Do not configure Storage RLS here (T1-6).
- **LOCKED decisions:** Part A §7, §13, §19, §20
- **Dependencies:** T1-2
- **Prerequisite tasks:** T1-2
- **Complexity:** M
- **Blocking:** YES — security requirement; no API routes may go live without RLS
- **Parallelizable:** Parallel with T1-3
- **Handoff:** M4 → M2, M5: RLS policies applied; share test matrix for IDOR tests
- **Acceptance criteria:**
  - Citizen A cannot SELECT citizen B's complaints via anon key
  - Admin can SELECT all complaints
  - Service role can INSERT audit_log; anon key cannot
- **Required tests:** RLS test suite (pytest with two different user JWTs + raw Supabase client)

---

#### T1-5: Authority seed data
- **Phase:** 1
- **Owner:** M4 (primary), M2 (support)
- **Objective:** Create immutable authority seed data from the Mangaluru authorities JSON.
- **Scope:**
  - Create `backend/data/mangaluru_authorities.json` with Mangaluru authority records
  - Create `supabase/seed/001_authorities.sql` — INSERT authority records from JSON
  - Authorities table must be populated before any complaint routing works
  - Add `DELETE`/`UPDATE` restriction via RLS (service role only; no application-level writes)
  - Each authority record must include: `id`, `name`, `categories[]`, `area_text`, `contact_email`, `phone` — per ADR-001 (§39) and updated §12
- **Non-goals:** Do not implement routing logic here (T3-2). Do not add ward_range, ward integers, or GeoJSON geometry — these are prohibited by ADR-001.
- **LOCKED decisions:** Part A §12 (ADR-001), §38 item 7 — authority data is immutable; routing is category + area_text only
- **Dependencies:** T1-4
- **Prerequisite tasks:** T1-4
- **Complexity:** M
- **Blocking:** YES — authority routing cannot be tested without seed data
- **Handoff:** M4 → M2, M3: authorities.json available; seed SQL applied; row count confirmed
- **Acceptance criteria:** `SELECT COUNT(*) FROM authorities` returns expected count; no application INSERT possible
- **Required tests:** Verify no INSERT via citizen JWT; verify seed row count

---

#### T1-6: Storage buckets and Storage RLS
- **Phase:** 1
- **Owner:** M4 (primary)
- **Objective:** Create all four Supabase Storage buckets and configure RLS policies per Part A §20.
- **Scope:**
  - Create buckets (via Supabase dashboard or migration API): `report-originals`, `report-redacted`, `resolution-photos`, `rti-documents`
  - All buckets: `public = false`
  - RLS policies per Part A §20:
    - `report-originals`: owner + admin read; service role write
    - `report-redacted`: owner + admin + authority_officer (assigned) read; service role write
    - `resolution-photos`: owner read; admin write; service role write
    - `rti-documents`: owner read/write; admin read
- **LOCKED decisions:** Part A §20 — no public buckets; signed URLs only (15-min expiry)
- **Dependencies:** T1-4
- **Prerequisite tasks:** T1-4
- **Complexity:** S
- **Blocking:** YES — image upload (T2-2) blocked until buckets exist
- **Parallelizable:** Parallel with T1-5
- **Handoff:** M4 → M2, M3: bucket names confirmed; storage RLS verified
- **Acceptance criteria:** All 4 buckets exist; citizen A cannot download citizen B's report-original; admin can
- **Required tests:** Storage RLS test (two citizen JWTs, cross-access denied)

---

#### T1-7: Audit log trigger
- **Phase:** 1
- **Owner:** M4 (primary)
- **Objective:** Create PostgreSQL trigger that auto-inserts into audit_log on complaint and RTI state changes.
- **Scope:**
  - Migration: `supabase/migrations/005_audit_trigger.sql`
  - Trigger on `complaints` UPDATE (status field) → INSERT into audit_log
  - Trigger on `rti_requests` UPDATE (status field) → INSERT into audit_log
  - Trigger on `complaints` INSERT → INSERT into audit_log
  - Log fields: entity_type, entity_id, action (INSERT/UPDATE), old_status, new_status, user_id (from `auth.uid()`)
- **Non-goals:** Do not log SELECT operations. Do not trigger on non-status field updates.
- **LOCKED decisions:** Part A §13 — immutable audit log; every state-changing action recorded
- **Dependencies:** T1-2, T1-4
- **Prerequisite tasks:** T1-2, T1-4
- **Complexity:** S
- **Blocking:** NO — functional but required before Phase 5 security sign-off
- **Parallelizable:** YES — parallel with T1-5, T1-6
- **Handoff:** M4 → M2, M5: trigger SQL applied; test with manual status update
- **Acceptance criteria:** Complaint status change → audit_log row created automatically
- **Required tests:** Update complaint status → verify audit_log INSERT

---

#### T1-8: Supabase Auth configuration and profile creation
- **Phase:** 1
- **Owner:** M4 (primary), M1 (support)
- **Objective:** Configure Supabase Auth (email/password), create profile auto-creation trigger, verify JWT payload.
- **Scope:**
  - Enable email/password auth in Supabase dashboard
  - Migration: `supabase/migrations/006_auth_trigger.sql`
  - Trigger on `auth.users` INSERT → auto-INSERT into `profiles` with role=citizen
  - Confirm JWT contains `user_id` (sub claim) and `role` (from app_metadata or profiles join)
  - Create demo user accounts: citizen_demo@civicai.test, admin_demo@civicai.test
  - Set admin_demo role=admin via Supabase dashboard (Part A §40 item 2)
- **Non-goals:** Do not implement frontend auth flow yet (T4-2). Do not implement OTP.
- **LOCKED decisions:** Part A §19 — Supabase Auth, RS256 JWT, three roles
- **Dependencies:** T1-2, T1-4
- **Prerequisite tasks:** T1-2, T1-4
- **Complexity:** S
- **Blocking:** YES — all auth-protected API tests require valid JWTs
- **Parallelizable:** Parallel with T1-7
- **Handoff:** M4 → M1, M2: demo user credentials + JWT sample shared (via secure channel)
- **Acceptance criteria:** Login → JWT returned; profile row auto-created with role=citizen; admin role set correctly
- **Required tests:** Login test; profile auto-creation test; JWT decode verification

---

### Phase 1 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T1-1: All 4 enums exist
- [ ] T1-2: All 7 tables exist with correct columns and FKs
- [ ] T1-3: All indexes created
- [ ] T1-4: RLS active; IDOR test passes
- [ ] T1-5: Authority seed data present
- [ ] T1-6: All 4 storage buckets exist with correct RLS
- [ ] T1-7: Audit trigger fires on status change
- [ ] T1-8: Auth working; demo users created; JWT verified

### Phase 1 Deliverables
- Complete Supabase schema
- RLS on all tables + storage
- Immutable authority seed data
- Working authentication
- Audit log trigger

---

## Phase 2 — AI / CV / LLM

### Objective
Implement the complete AI and computer vision pipeline: image validation,
privacy redaction (faces + plates), YOLO detection, taxonomy mapping,
confidence scoring, LLM integration with fallback, and RAG/embedding infrastructure.
Runs in parallel with Phase 3 after Phase 1 completes.

### Entry Criteria
- Phase 1 all gates passed
- Supabase Storage buckets exist (T1-6)
- `backend/requirements.txt` exists (T0-3)

### Phase 2 Tasks

---

#### T2-1: AI dependency installation and RAM validation
- **Phase:** 2
- **Owner:** M3 (primary), M5 (support)
- **Objective:** Add all AI/CV dependencies to requirements.txt and validate RAM budget on Render.
- **Scope:**
  - Add to `backend/requirements.txt`: `ultralytics`, `opencv-python-headless`, `fast-alpr`, `sentence-transformers`, `groq`
  - Create `backend/cv/ram_check.py` — utility to measure available RAM at runtime
  - RAM gate logic: if `psutil.available_memory() < 512MB` → set `EMBEDDING_ENABLED=False`
  - Document expected memory footprint per model (Part A §8, §29)
- **Non-goals:** Do not load any model at startup. Do not implement CV logic yet.
- **LOCKED decisions:** Part A §8 — lazy loading; RAM gate for BAAI; 512 MB Render limit
- **Dependencies:** T0-3
- **Prerequisite tasks:** T0-3
- **Complexity:** S
- **Blocking:** YES — all CV tasks depend on dependencies being installed
- **Parallelizable:** YES — can start when T0-3 is done, independent of Phase 1
- **Handoff:** M3 → M2: requirements.txt updated; ram_check.py available
- **Acceptance criteria:** `pip install -r requirements.txt` succeeds; ram_check.py returns available RAM
- **Required tests:** `pytest` — test ram_check.py returns a positive integer

---

#### T2-2: Image validation and upload handler
- **Phase:** 2
- **Owner:** M3 (primary), M2 (support)
- **Objective:** Implement image upload validation (MIME, magic bytes, size, dimensions) per Part A §13, §28.
- **Scope:**
  - Create `backend/cv/image_validator.py`
  - Validate MIME type (accept only image/jpeg, image/png, image/webp)
  - Validate magic bytes (not just Content-Type header)
  - Validate file size (max 10 MB)
  - Validate minimum dimensions (min 200×200 px)
  - Pillow re-encode to strip metadata (EXIF, etc.)
  - Resize to max 1024px longest side for CV inference (Part A §29)
  - Raise typed exceptions for each failure mode
- **Non-goals:** Do not store the image here. Do not run CV inference here.
- **LOCKED decisions:** Part A §13, §28 — MIME + magic bytes check; Pillow re-encode
- **Dependencies:** T2-1, T1-6
- **Prerequisite tasks:** T2-1
- **Complexity:** S
- **Blocking:** YES — privacy pipeline (T2-3) depends on validated image
- **Parallelizable:** NO (sequential within Phase 2)
- **Handoff:** M3 → M2: image_validator.py API; test fixtures created
- **Acceptance criteria:** Malformed MIME rejected; oversized file rejected; valid JPEG accepted and re-encoded
- **Required tests:** pytest — malformed MIME, oversized, non-image, valid image (4 tests minimum)

---

#### T2-3: Privacy redaction — face detection
- **Phase:** 2
- **Owner:** M3 (primary)
- **Objective:** Implement YuNet ONNX face detection and Pillow Gaussian blur redaction.
- **Scope:**
  - Create `backend/cv/privacy.py` — `redact_faces(image: PIL.Image) → PIL.Image`
  - Load YuNet ONNX model lazily on first call (Part A §8)
  - Detect all faces using YuNet
  - Apply Gaussian blur (radius=20) to each detected face bounding box
  - Return redacted PIL image
  - If no faces detected: return image unchanged
- **Non-goals:** Do not detect plates here (T2-4). Do not store image here.
- **LOCKED decisions:** Part A §8 — YuNet ONNX; Part A §14 — blur before storage
- **Dependencies:** T2-2
- **Prerequisite tasks:** T2-2
- **Complexity:** M
- **Blocking:** YES — redaction must complete before storage (Part A §14, §38 item 6)
- **Parallelizable:** NO (sequential within privacy pipeline)
- **Handoff:** M3: privacy.py `redact_faces` function ready; test images with faces prepared
- **Acceptance criteria:** Test image with face → blurred face in output; test image without face → unchanged
- **Required tests:** pytest — image with face (blur applied), image without face (unchanged), model loads lazily

---

#### T2-4: Privacy redaction — licence plate detection
- **Phase:** 2
- **Owner:** M3 (primary)
- **Objective:** Implement fast-alpr licence plate detection and black rectangle redaction.
- **Scope:**
  - Extend `backend/cv/privacy.py` — `redact_plates(image: PIL.Image) → PIL.Image`
  - Load fast-alpr model lazily on first call
  - Detect all licence plates using fast-alpr
  - Apply black rectangle over each detected plate bounding box
  - Return redacted PIL image
  - If no plates detected: return image unchanged
- **Non-goals:** Do not do OCR on plates. Do not store image here.
- **LOCKED decisions:** Part A §8 — fast-alpr; Part A §14 — redaction before storage
- **Dependencies:** T2-3
- **Prerequisite tasks:** T2-3
- **Complexity:** M
- **Blocking:** YES — full privacy redaction must complete before storage
- **Parallelizable:** NO
- **Handoff:** M3: `redact_plates` function ready; test images with plates prepared
- **Acceptance criteria:** Test image with plate → plate blacked out; test image without plate → unchanged
- **Required tests:** pytest — image with plate, image without plate, model loads lazily

---

#### T2-5: YOLO object detection and taxonomy mapping
- **Phase:** 2
- **Owner:** M3 (primary)
- **Objective:** Implement YOLOv8n detection and map YOLO classes to civic issue taxonomy.
- **Scope:**
  - Create `backend/cv/detection.py` — `detect_civic_issue(image: PIL.Image) → DetectionResult`
  - Load YOLOv8n model lazily on first call
  - Run YOLO inference on resized image
  - Return top-1 prediction class + confidence score
  - Create `backend/cv/taxonomy.py` — `map_to_category(yolo_class: str) → IssueCategory`
  - Mapping table: YOLO class names → `issue_category` enum values
  - If YOLO class has no mapping → return `IssueCategory.other`
- **Non-goals:** Do not run LLM here. Do not compute authority routing here.
- **LOCKED decisions:** Part A §8 — YOLOv8n; Part A §9 — LLM classifies if confidence <0.5
- **Dependencies:** T2-2
- **Prerequisite tasks:** T2-2
- **Complexity:** M
- **Blocking:** YES — confidence scoring (T2-6) and LLM (T2-8) depend on detection result
- **Parallelizable:** Parallel with T2-3/T2-4 after T2-2
- **Handoff:** M3 → M2: `DetectionResult` schema; taxonomy.py mapping table
- **Acceptance criteria:** Pothole image → returns `IssueCategory.pothole` with confidence > 0; unknown class → `other`
- **Required tests:** pytest — known civic image, unknown image, lazy load test

---

#### T2-6: Evidence confidence scoring
- **Phase:** 2
- **Owner:** M3 (primary)
- **Objective:** Implement evidence confidence score computation per Part A §8.
- **Scope:**
  - Create `backend/cv/confidence.py` — `compute_confidence(detection_confidence: float, category: IssueCategory) → float`
  - Score = detection_confidence × category_relevance_weight
  - Category relevance weights table (e.g., pothole=1.0, other=0.4)
  - Output range: 0.0–1.0
- **LOCKED decisions:** Part A §8 — confidence = detection confidence × category relevance
- **Dependencies:** T2-5
- **Prerequisite tasks:** T2-5
- **Complexity:** S
- **Blocking:** NO — pipeline works with raw detection confidence; scoring is advisory
- **Parallelizable:** YES — after T2-5
- **Handoff:** M3 → M2: confidence.py API; weight table documented
- **Acceptance criteria:** High-confidence pothole detection → score > 0.7; low-confidence other → score < 0.5
- **Required tests:** pytest — boundary values, weight table coverage

---

#### T2-7: Image hash (blake3) and duplicate detection
- **Phase:** 2
- **Owner:** M3 (primary), M2 (support)
- **Objective:** Compute blake3 hash of original image for duplicate detection.
- **Scope:**
  - In `backend/cv/pipeline.py`: compute `blake3(original_image_bytes) → hex_str`
  - Duplicate check query: `reports WHERE image_hash = ? AND ST_DWithin(location, ?, 50)` (PostGIS)
  - Return `is_duplicate: bool` + `duplicate_report_id: UUID | None`
- **Non-goals:** Do not block submission on duplicate — only flag as advisory.
- **LOCKED decisions:** Part A §11 — 50m PostGIS duplicate check; Part A §39 — blake3
- **Dependencies:** T2-2, T1-2
- **Prerequisite tasks:** T2-2, T1-2
- **Complexity:** S
- **Blocking:** NO — duplicate flag is advisory; does not block submission
- **Parallelizable:** YES
- **Handoff:** M3 → M2: hash function available; duplicate query SQL tested
- **Acceptance criteria:** Same image bytes → same hash; ST_DWithin query returns duplicate when within 50m
- **Required tests:** pytest — same image, different image, nearby location

---

#### T2-8: LLM integration — Groq provider
- **Phase:** 2
- **Owner:** M3 (primary)
- **Objective:** Implement Groq API integration with structured output and Pydantic schema validation.
- **Scope:**
  - Create `backend/llm/prompts.py` — prompt templates for: complaint description generation, RTI draft, ambiguous category classification
  - Create `backend/llm/groq_provider.py` — async Groq API call; return structured JSON
  - Create `backend/llm/output_validator.py` — Pydantic model for LLM output; validate all fields
  - LLM output schema: `{category, description (max 500), authority_recommendation, confidence}`
  - All citizen-provided text sanitized before prompt injection (Part A §13)
  - Prompt injection protection: strip special tokens, limit input length
- **Non-goals:** Do not wire Watsonx stub. Do not implement fallback here (T2-9).
- **LOCKED decisions:** Part A §9 — Groq llama-3.1-8b-instant; output schema; prompt injection protection
- **Dependencies:** T2-1
- **Prerequisite tasks:** T2-1
- **Complexity:** M
- **Blocking:** YES — LLM fallback (T2-9) wraps this; pipeline orchestrator (T2-11) uses both
- **Parallelizable:** YES — parallel with T2-3/T2-4/T2-5 after T2-1
- **Handoff:** M3 → M2: Groq provider API; test with mock Groq response
- **Acceptance criteria:** Valid Groq response → Pydantic model populated; invalid JSON → exception raised; prompt injection string sanitized
- **Required tests:** pytest — valid response, invalid JSON, schema violation, prompt injection test

---

#### T2-9: LLM fallback — deterministic template engine
- **Phase:** 2
- **Owner:** M3 (primary)
- **Objective:** Implement deterministic template-based LLM fallback per Part A §9.
- **Scope:**
  - Create `backend/llm/fallback_provider.py`
  - Templates for all three use cases: complaint description, RTI draft, category classification
  - Input: `{category, location, confidence, address}` → output: same Pydantic schema as Groq
  - Used when: Groq is unavailable, rate-limited, or returns invalid schema
  - Create `backend/llm/watsonx_stub.py` — provider interface stub (NOT wired; method raises NotImplementedError)
- **Non-goals:** Do not wire Watsonx. Do not call any external API.
- **LOCKED decisions:** Part A §9 — deterministic fallback; IBM Watsonx stub not wired
- **Dependencies:** T2-8
- **Prerequisite tasks:** T2-8
- **Complexity:** S
- **Blocking:** YES — fallback must be ready before pipeline goes live
- **Parallelizable:** NO
- **Handoff:** M3 → M2: fallback_provider.py; watsonx_stub.py ready
- **Acceptance criteria:** Fallback returns valid Pydantic output for all three use cases; Groq failure → fallback used automatically
- **Required tests:** pytest — Groq mock failure → fallback triggered; fallback output matches schema

---

#### T2-10: LLM service orchestrator
- **Phase:** 2
- **Owner:** M3 (primary), M2 (support)
- **Objective:** Create llm_service.py that selects Groq or fallback transparently.
- **Scope:**
  - Create `backend/services/llm_service.py`
  - `generate_complaint_description(cv_result, location, address) → LLMOutput`
  - `generate_rti_draft(complaint, rag_context) → LLMOutput`
  - `classify_category(image_context) → IssueCategory`
  - Try Groq → if exception or schema failure → use fallback
  - Log which provider was used (audit)
- **LOCKED decisions:** Part A §9 — provider chain: Groq → deterministic
- **Dependencies:** T2-8, T2-9
- **Prerequisite tasks:** T2-8, T2-9
- **Complexity:** S
- **Blocking:** YES — AI pipeline orchestrator (T2-11) uses this
- **Parallelizable:** NO
- **Handoff:** M3 → M2: llm_service.py API stable
- **Acceptance criteria:** Groq available → Groq used; Groq unavailable → fallback used; both return same schema
- **Required tests:** pytest — both paths tested; schema consistency check

---

#### T2-11: AI pipeline orchestrator
- **Phase:** 2
- **Owner:** M3 (primary), M2 (support)
- **Objective:** Integrate all CV + LLM steps into a single pipeline function per Part A §23.
- **Scope:**
  - Create `backend/cv/pipeline.py` — `run_ai_pipeline(image_bytes, location) → AIResult`
  - Sequential steps per Part A §23 AI Flow diagram
  - Returns: `{redacted_image_bytes, category, confidence, authority_recommendation, description, image_hash, is_duplicate, duplicate_report_id, llm_provider_used}`
  - Handles partial failures gracefully (e.g., YOLO fails → category=other)
  - Memory cleanup after each model call (del model reference, gc.collect)
- **Non-goals:** Do not store images or DB records here — that is the service layer (T3-1).
- **LOCKED decisions:** Part A §8 (RAM/lazy load), §23 (AI flow), §29 (performance)
- **Dependencies:** T2-3, T2-4, T2-5, T2-6, T2-7, T2-10
- **Prerequisite tasks:** T2-3, T2-4, T2-5, T2-6, T2-7, T2-10
- **Complexity:** L
- **Blocking:** YES — report workflow (T3-1) uses this pipeline
- **Parallelizable:** NO (integration task)
- **Handoff:** M3 → M2: pipeline.py `run_ai_pipeline` API; AIResult schema; test fixtures
- **Acceptance criteria:** End-to-end test image → returns complete AIResult; memory does not exceed 400 MB after pipeline run
- **Required tests:** pytest — end-to-end with test image; memory usage test; partial failure recovery test

---

#### T2-12: RAG infrastructure — embedding and vector store
- **Phase:** 2
- **Owner:** M3 (primary), M4 (support)
- **Objective:** Implement BAAI embedding with RAM gate and pgvector semantic search for RTI.
- **Scope:**
  - Create `backend/rag/embedder.py` — `embed(text) → list[float] | None`
  - RAM gate: if RAM check fails → return None (keyword fallback activates)
  - Load BAAI/bge-large-en-v1.5 lazily; vector dimension = 1536
  - Create `backend/rag/vector_store.py` — `search(embedding, top_k=5) → list[KnowledgeChunk]`
  - pgvector cosine similarity query on `rti_knowledge_base`
  - Create `backend/rag/retriever.py` — `retrieve_context(query_text) → list[KnowledgeChunk]`
  - If embedding available → vector search; else → keyword ILIKE search fallback
- **LOCKED decisions:** Part A §10 — BAAI only if RAM available; keyword fallback; Part A §8 RAM gate
- **Dependencies:** T2-1, T1-3
- **Prerequisite tasks:** T2-1, T1-3
- **Complexity:** M
- **Blocking:** NO — RTI draft works without RAG (fallback exists); but RAG quality requires this
- **Parallelizable:** YES — parallel with T2-8 through T2-11
- **Handoff:** M3 → M2: retriever.py API; test with sample knowledge base entries
- **Acceptance criteria:** With RAM available → vector search returns top-5 chunks; without RAM → keyword search returns results; RAM gate correctly disables embedding
- **Required tests:** pytest — vector search (mocked pgvector), keyword fallback, RAM gate disabled path

---

#### T2-13: RTI knowledge base ingestion
- **Phase:** 2
- **Owner:** M3 (primary), M4 (support)
- **Objective:** Create and ingest RTI knowledge base documents into rti_knowledge_base table.
- **Scope:**
  - Create `backend/rag/chunker.py` — chunk documents into max-512-token segments
  - Create `supabase/seed/002_rti_knowledge_base.sql` OR Python ingestion script
  - Content: RTI Act sections, Mangaluru MCC complaint procedures, Karnataka civic rights (summary)
  - Embed each chunk using embedder.py (if available) → INSERT into `rti_knowledge_base`
  - If embedding unavailable → insert chunks with NULL embedding (keyword-only fallback still works)
- **LOCKED decisions:** Part A §10 — chunking max 512 tokens; pgvector storage
- **Dependencies:** T2-12, T1-2
- **Prerequisite tasks:** T2-12, T1-2
- **Complexity:** M
- **Blocking:** NO — RTI draft uses fallback if knowledge base is empty
- **Parallelizable:** YES
- **Handoff:** M3 → M2: knowledge base seeded; row count confirmed; sample retrieval tested
- **Acceptance criteria:** `SELECT COUNT(*) FROM rti_knowledge_base` > 0; retrieval returns relevant chunks for RTI query
- **Required tests:** pytest — retrieval test with known query

---

### Phase 2 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T2-1: All AI dependencies install cleanly; ram_check.py works
- [ ] T2-2: Image validation rejects malformed inputs; accepts valid images
- [ ] T2-3: Face redaction blurs detected faces
- [ ] T2-4: Plate redaction blacks out detected plates
- [ ] T2-5: YOLO detection + taxonomy mapping returns correct category
- [ ] T2-6: Confidence scoring returns values in 0.0–1.0 range
- [ ] T2-7: blake3 hash + duplicate check query works
- [ ] T2-8: Groq provider returns valid schema output
- [ ] T2-9: Fallback provider returns valid schema output; activates on Groq failure
- [ ] T2-10: LLM service orchestrator uses correct provider
- [ ] T2-11: End-to-end AI pipeline returns AIResult; memory within budget
- [ ] T2-12: RAG retriever returns chunks (vector or keyword)
- [ ] T2-13: RTI knowledge base seeded

### Phase 2 Deliverables
- Complete AI/CV pipeline (`cv/pipeline.py`)
- Privacy redaction (face + plate)
- YOLO + taxonomy + confidence
- LLM service with Groq + fallback
- RAG infrastructure
- RTI knowledge base seeded

---

## Phase 3 — Backend / API Services

### Objective
Implement all FastAPI routes, service layer, repositories, authority routing,
complaint workflow, RTI workflow, mock government submission, Realtime publishing,
and security middleware. Runs in parallel with Phase 2 after Phase 1 completes.

### Entry Criteria
- Phase 1 all gates passed
- Phase 2 AI pipeline complete (T2-11) for report service integration
- Backend bootstrap complete (T0-3)

> Note: Phase 3 can begin its non-AI tasks (T3-3 through T3-7) immediately after Phase 1.
> T3-1 (report service) requires T2-11 from Phase 2.

### Phase 3 Tasks

---

#### T3-1: Backend core infrastructure — dependencies, auth middleware, RBAC
- **Phase:** 3
- **Owner:** M2 (primary), M4 (support)
- **Objective:** Implement FastAPI dependencies: JWT verification, RBAC, IDOR ownership check, rate limiting.
- **Scope:**
  - Create `backend/security/jwt_verify.py` — verify Supabase JWT RS256; extract user_id + role
  - Create `backend/security/rbac.py` — `require_role(role: UserRole)` FastAPI dependency
  - Create `backend/security/ownership.py` — `verify_ownership(entity_user_id, current_user_id)`
  - Create `backend/security/input_sanitizer.py` — strip LLM-injection chars from text fields
  - Create `backend/dependencies.py` — `get_current_user()`, `get_db()`, `get_limiter()`
  - Configure slowapi rate limiter: 10 req/min for AI endpoints, 60 req/min standard
  - Configure CORS: allow only `ALLOWED_ORIGINS` env var (Vercel domain + localhost)
- **Non-goals:** Do not implement business routes yet.
- **LOCKED decisions:** Part A §13, §19 — JWT RS256; RBAC; IDOR; rate limiting; CORS
- **Dependencies:** T0-3, T1-8
- **Prerequisite tasks:** T0-3, T1-8
- **Complexity:** M
- **Blocking:** YES — all authenticated routes depend on this
- **Parallelizable:** YES — parallel with Phase 2 tasks
- **Handoff:** M2 → M1, M3: auth dependency API; test with demo user JWT
- **Acceptance criteria:** Valid JWT → user extracted; invalid JWT → 401; wrong role → 403; rate limit exceeded → 429
- **Required tests:** pytest — valid JWT, invalid JWT, expired JWT, wrong role, rate limit

---

#### T3-2: Authority routing service
- **Phase:** 3
- **Owner:** M2 (primary), M4 (support)
- **Objective:** Implement authority routing from immutable JSON per Part A §12 and ADR-001.
- **Scope:**
  - Create `backend/services/authority_service.py`
  - Load `mangaluru_authorities.json` at service startup (read-only, cached in memory)
  - `route_to_authority(category: IssueCategory, address_text: str | None) → Authority`
  - Step 1: filter authorities whose `categories` array includes the complaint category
  - Step 2: if multiple match and `address_text` is provided → keyword match against authority `area_text` field (case-insensitive substring)
  - Step 3: if no text match or no address_text → return first category-matching authority (category default)
  - Citizen override: `get_authority_by_id(id)` for citizen selection from the full authority list
  - Create `backend/db/repositories/authority_repo.py` — reads from JSON only (NOT database)
- **Non-goals:** Do not write to authorities table. Do not use PostGIS for routing. Do not use ward_range integers, GeoJSON polygons, or ward_number fields for routing. These are prohibited by ADR-001.
- **LOCKED decisions:** Part A §12 (ADR-001) — immutable JSON; routing by category + area_text keyword only; citizen may override
- **Dependencies:** T1-5, T3-1
- **Prerequisite tasks:** T1-5, T3-1
- **Complexity:** M
- **Blocking:** YES — report service (T3-3) requires authority routing
- **Parallelizable:** YES — parallel with other Phase 3 tasks
- **Handoff:** M2: authority_service.py API; test with all categories; confirm no PostGIS calls in routing path
- **Acceptance criteria:** All 10 issue categories return a valid authority; address_text keyword match selects correct authority when multiple match; no-match → first category default returned; no ward_range or PostGIS used
- **Required tests:** pytest — all 10 categories, address_text keyword match, no-match fallback, no PostGIS dependency

---

#### T3-3: Report service and report router
- **Phase:** 3
- **Owner:** M2 (primary), M3 (support)
- **Objective:** Implement report creation workflow: image upload → AI pipeline → DB record.
- **Scope:**
  - Create `backend/db/repositories/report_repo.py` — INSERT/SELECT reports
  - Create `backend/services/report_service.py` — orchestrates: validate → AI pipeline → store original + redacted → insert DB record
  - Create `backend/routers/reports.py`:
    - `POST /reports/` — multipart upload; triggers AI pipeline; returns report with AI results
    - `GET /reports/{id}` — returns report + signed URLs for images
  - No route handler contains business logic — all in service layer
  - Signed URLs: backend generates 15-min signed URLs via Supabase Storage client
- **LOCKED decisions:** Part A §6 (service layer rule), §18 (API contract), §20 (signed URLs), §22 (data flow)
- **Dependencies:** T2-11, T3-1, T3-2, T1-6
- **Prerequisite tasks:** T2-11, T3-1, T3-2, T1-6
- **Complexity:** L
- **Blocking:** YES — complaint service (T3-4) depends on reports existing
- **Parallelizable:** NO (requires AI pipeline)
- **Handoff:** M2 → M1: `POST /reports/` API contract stable; test with Postman/pytest
- **Acceptance criteria:** Upload valid image → report created in DB → AI results returned; upload invalid image → 422; wrong user JWT → 401
- **Required tests:** pytest — valid upload, invalid MIME, oversized, auth failure, AI result schema

---

#### T3-4: Complaint service and complaint router
- **Phase:** 3
- **Owner:** M2 (primary)
- **Objective:** Implement complaint CRUD, approval, and mock government submission per Part A §15, §24.
- **Scope:**
  - Create `backend/db/repositories/complaint_repo.py`
  - Create `backend/services/complaint_service.py`:
    - `create_complaint(report_id, user_id, overrides)` — create from approved report
    - `submit_complaint(complaint_id, user_id)` — validate state machine transition DRAFT→SUBMITTED; generate mock_gov_ref; publish Realtime event
    - `update_status(complaint_id, new_status, admin_user)` — admin state transitions; enforce state machine
    - `resolve_complaint(complaint_id, resolution_photo, notes, admin_user)` — RESOLVED transition + storage
  - Create `backend/routers/complaints.py` per Part A §18 API contract
  - Mock gov ref: `f"MCC-{uuid4().hex[:8].upper()}"` — no external API called
  - All state transitions validated against complaint state machine (Part A §24)
- **LOCKED decisions:** Part A §15, §24 — state machine; §38 item 4 — no submission without approval; §13 — mock gov only
- **Dependencies:** T3-1, T3-3
- **Prerequisite tasks:** T3-1, T3-3
- **Complexity:** L
- **Blocking:** YES — RTI service depends on complaint status
- **Parallelizable:** NO
- **Handoff:** M2 → M1: complaints API stable; state machine transitions documented
- **Acceptance criteria:** DRAFT→SUBMITTED transition works; invalid transition (e.g., RESOLVED→SUBMITTED) rejected with 409; mock_gov_ref generated; admin cannot submit on behalf of citizen
- **Required tests:** pytest — all valid transitions, all invalid transitions, IDOR test, mock gov ref format

---

#### T3-5: RTI service and RTI router
- **Phase:** 3
- **Owner:** M2 (primary), M3 (support)
- **Objective:** Implement RTI eligibility check, draft generation, approval, and mock submission per Part A §16, §25.
- **Scope:**
  - Create `backend/db/repositories/rti_repo.py`
  - Create `backend/services/rti_service.py`:
    - `check_eligibility(complaint_id, user_id)` — verify 30-day rule + status check + no existing RTI
    - `create_rti_draft(complaint_id, user_id)` — RAG retrieval → LLM draft → INSERT rti_requests (status=DRAFT)
    - `approve_rti(rti_id, user_id)` — DRAFT→SUBMITTED transition; generate rti_ref; mock RTI submission
    - `update_rti_status(rti_id, new_status, admin)` — admin demo state transitions
  - Create `backend/routers/rti.py` per Part A §18
  - Mock RTI ref: `f"RTI-MCC-{uuid4().hex[:8].upper()}"`
  - After submission: auto-transition to ACKNOWLEDGED (mock)
- **LOCKED decisions:** Part A §16, §25 — RTI lifecycle and state machine; §38 item 8 — 30-day eligibility
- **Dependencies:** T3-1, T3-4, T2-10, T2-12
- **Prerequisite tasks:** T3-1, T3-4, T2-10, T2-12
- **Complexity:** L
- **Blocking:** NO — RTI is separate flow from complaint submission
- **Parallelizable:** YES — parallel with T3-6, T3-7
- **Handoff:** M2 → M1: RTI API contract stable; mock rti_ref format documented
- **Acceptance criteria:** Eligible complaint → RTI draft created; ineligible (resolved/too recent) → 422; mock rti_ref generated; IDOR test passes
- **Required tests:** pytest — eligibility pass, eligibility fail (resolved), eligibility fail (too recent), IDOR, state transitions

---

#### T3-6: Admin router and admin service
- **Phase:** 3
- **Owner:** M2 (primary)
- **Objective:** Implement admin endpoints per Part A §18.
- **Scope:**
  - Create `backend/routers/admin.py`:
    - `GET /admin/complaints` — paginated list of all complaints (admin role required)
    - `PATCH /complaints/{id}/status` — admin status update
    - `POST /complaints/{id}/resolve` — admin resolution with photo upload
  - All admin routes require `role=admin` (RBAC check via dependency)
  - Use complaint_service methods; no duplicate logic
- **LOCKED decisions:** Part A §19 — admin role; Part A §18 — API contract
- **Dependencies:** T3-1, T3-4
- **Prerequisite tasks:** T3-1, T3-4
- **Complexity:** M
- **Blocking:** NO — can be implemented after complaint service
- **Parallelizable:** YES
- **Handoff:** M2 → M1: admin API endpoints stable
- **Acceptance criteria:** Admin JWT → list all complaints; citizen JWT → 403; status update triggers audit log
- **Required tests:** pytest — admin access, citizen 403, status update + audit log

---

#### T3-7: Supabase Realtime publishing
- **Phase:** 3
- **Owner:** M2 (primary), M4 (support)
- **Objective:** Publish Realtime events on complaint status changes per Part A §22.
- **Scope:**
  - Create `backend/services/realtime_service.py`
  - Publish to Supabase Realtime channel `complaints:{complaint_id}` on every status change
  - Event payload: `{complaint_id, new_status, updated_at}`
  - Called from complaint_service.submit_complaint and complaint_service.update_status
- **LOCKED decisions:** Part A §22 — Realtime on SUBMITTED + RESOLVED + REJECTED transitions
- **Dependencies:** T3-4
- **Prerequisite tasks:** T3-4
- **Complexity:** S
- **Blocking:** NO — status updates work without Realtime; Realtime is UX enhancement
- **Parallelizable:** YES
- **Handoff:** M2 → M1: Realtime channel name + event schema documented
- **Acceptance criteria:** Complaint status change → Realtime event published with correct payload
- **Required tests:** pytest (integration) — mock Supabase Realtime; event payload matches schema

---

### Phase 3 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T3-1: Auth middleware; JWT verify; RBAC; IDOR; rate limiting all working
- [ ] T3-2: Authority routing returns correct authority for all categories
- [ ] T3-3: POST /reports/ creates report with AI results; GET /reports/{id} returns signed URLs
- [ ] T3-4: Complaint CRUD + all state transitions enforced; mock_gov_ref generated
- [ ] T3-5: RTI eligibility check + draft creation + mock submission working
- [ ] T3-6: Admin endpoints protected by RBAC; admin list works
- [ ] T3-7: Realtime events published on status change

### Phase 3 Deliverables
- Complete FastAPI service layer
- All API endpoints per Part A §18
- Complaint + RTI state machines enforced
- Authority routing from immutable JSON
- Mock government submission
- Supabase Realtime publishing
- Security middleware active


---

## Phase 4 — Frontend / PWA

### Objective
Implement the complete Next.js frontend: authentication flow, camera capture,
AI analysis review, complaint submission, complaint status, RTI flow, admin screens,
Supabase Realtime subscriptions, PWA service worker, and offline DRAFT_OFFLINE flow.

### Entry Criteria
- Phase 1 all gates passed (auth + DB)
- Phase 3 API contracts stable (T3-1 through T3-7 complete)
- Phase 2 AI pipeline complete (AI results schema stable)

### Phase 4 Tasks

---

#### T4-1: Frontend Supabase client and API client
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Configure Supabase browser client and typed API client for FastAPI backend.
- **Scope:**
  - Create `frontend/lib/supabase.ts` — Supabase browser client using env vars
  - Create `frontend/lib/api-client.ts` — typed fetch wrapper for FastAPI; attaches JWT Bearer; handles `{"data":..., "error":...}` envelope
  - Create `frontend/lib/types.ts` — TypeScript types matching Pydantic schemas (Complaint, Report, RTI, Authority, etc.)
  - Error handling: API error envelope → typed FrontendError; network error → retry hint
- **Non-goals:** Do not implement any UI yet.
- **LOCKED decisions:** Part A §18 — API envelope; Part A §19 — JWT Bearer
- **Dependencies:** T0-2, T1-8, T3-1
- **Prerequisite tasks:** T0-2, T1-8, T3-1
- **Complexity:** S
- **Blocking:** YES — all frontend pages depend on these clients
- **Parallelizable:** NO
- **Handoff:** M1: lib/supabase.ts + lib/api-client.ts ready; TypeScript types documented
- **Acceptance criteria:** API client sends correct JWT header; error envelope parsed correctly; TypeScript types compile without errors
- **Required tests:** Jest — mock fetch; valid envelope; error envelope; missing JWT

---

#### T4-2: Authentication pages — login, register, session
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement login, register pages and session management using Supabase Auth.
- **Scope:**
  - Create `frontend/app/(auth)/login/page.tsx` — email/password login form (Zod + react-hook-form)
  - Create `frontend/app/(auth)/register/page.tsx` — registration form
  - Create `frontend/lib/auth-context.tsx` — React Context: current user, session, role
  - Create `frontend/middleware.ts` — Next.js middleware: redirect unauthenticated users to /login
  - Session: Supabase client auto-refreshes JWT; store session in context
  - On login success → redirect to /dashboard
- **Non-goals:** Do not implement OTP. Do not implement social login.
- **LOCKED decisions:** Part A §19 — Supabase Auth; email/password; React Context for session
- **Dependencies:** T4-1
- **Prerequisite tasks:** T4-1
- **Complexity:** S
- **Blocking:** YES — all authenticated pages need session
- **Parallelizable:** NO
- **Handoff:** M1: login flow working; session context available to all pages
- **Acceptance criteria:** Login → session set → redirect to dashboard; invalid credentials → error shown; protected route without session → redirect to login
- **Required tests:** Jest + RTL — login form submit, invalid credentials, redirect behavior

---

#### T4-3: Dashboard — complaint list and status overview
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement dashboard page showing citizen's complaints and statuses.
- **Scope:**
  - Create `frontend/app/dashboard/page.tsx`
  - SWR fetch: `GET /complaints/` → list citizen's complaints
  - Display complaint cards: category, status badge (color-coded), submitted_at, authority name
  - "New Report" CTA button → /report/new
  - "Pending Drafts" section: show DRAFT_OFFLINE items from IndexedDB
  - Loading skeleton; empty state
- **LOCKED decisions:** Part A §5 — React Context + SWR; Part A §17 — DRAFT_OFFLINE in IndexedDB
- **Dependencies:** T4-1, T4-2, T3-4
- **Prerequisite tasks:** T4-1, T4-2
- **Complexity:** S
- **Blocking:** NO
- **Parallelizable:** YES — parallel with T4-4 after T4-2
- **Handoff:** M1: dashboard page complete; Pending Drafts section implemented
- **Acceptance criteria:** Complaint list loads and renders; DRAFT_OFFLINE items appear in pending section; empty state shown when no complaints
- **Required tests:** Jest + RTL — render with complaints, empty state, pending drafts

---

#### T4-4: Camera capture component
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement camera-first photo capture using MediaDevices API per Part A §38 item 1.
- **Scope:**
  - Create `frontend/components/camera/CameraCapture.tsx`
  - Use `navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}})` for rear camera
  - Live viewfinder in UI
  - Capture button → `canvas.toBlob()` → returns JPEG blob
  - Show captured preview with "Retake" and "Use Photo" buttons
  - If camera unavailable → show error message (do NOT fall back to file input in main flow)
- **Non-goals:** Do not implement gallery upload fallback. Camera is mandatory in main flow.
- **LOCKED decisions:** Part A §1, §38 item 1 — camera-first, no gallery in main flow
- **Dependencies:** T4-2
- **Prerequisite tasks:** T4-2
- **Complexity:** M
- **Blocking:** YES — report creation page (T4-5) uses this component
- **Parallelizable:** YES — parallel with T4-3
- **Handoff:** M1: CameraCapture.tsx component ready; returns blob via callback
- **Acceptance criteria:** Camera opens; photo captured; preview shown; "Retake" resets; blob returned via callback; error shown if camera unavailable
- **Required tests:** Jest + RTL — mock getUserMedia; capture; retake; camera error

---

#### T4-5: GPS acquisition and MapLibre location component
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement GPS acquisition with MapLibre fallback pin per Part A §11.
- **Scope:**
  - Create `frontend/components/map/LocationPicker.tsx`
  - Attempt `navigator.geolocation.getCurrentPosition()` → show GPS coordinates
  - If GPS available → display on MapLibre map with pin at GPS location
  - If GPS unavailable or denied → show MapLibre map; citizen manually pins location
  - MapLibre: use OpenFreeMap tiles; initialize with Mangaluru viewport (lat:12.9, lng:74.85)
  - Return `{lat, lng}` via callback
- **LOCKED decisions:** Part A §11 — MapLibre GL JS 4.x; OpenFreeMap; GPS with manual fallback
- **Dependencies:** T4-2
- **Prerequisite tasks:** T4-2
- **Complexity:** M
- **Blocking:** YES — report creation page (T4-6) uses this
- **Parallelizable:** YES — parallel with T4-4
- **Handoff:** M1: LocationPicker.tsx ready; GPS + manual pin both tested
- **Acceptance criteria:** GPS available → pin at GPS location; GPS unavailable → empty map; manual pin → location returned; Mangaluru viewport default
- **Required tests:** Jest + RTL — mock geolocation; GPS success; GPS fail; manual pin

---

#### T4-6: Report creation page — camera → upload → AI waiting
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement report/new flow: camera capture → GPS → upload to API → AI processing status.
- **Scope:**
  - Create `frontend/app/report/new/page.tsx`
  - Step 1: CameraCapture component → captured blob
  - Step 2: LocationPicker component → lat/lng
  - Step 3: POST to `POST /reports/` (multipart: image + location)
  - Step 4: Show AI processing spinner while waiting for response
  - On success → redirect to report/[id]/review
  - On failure → show error + retry option
  - If offline: save to IndexedDB as DRAFT_OFFLINE; show "Saved offline" message
- **LOCKED decisions:** Part A §15 (lifecycle), §17 (offline DRAFT_OFFLINE), §38 items 1,2
- **Dependencies:** T4-4, T4-5, T3-3
- **Prerequisite tasks:** T4-4, T4-5, T3-3
- **Complexity:** M
- **Blocking:** YES — review page (T4-7) comes after this
- **Parallelizable:** NO
- **Handoff:** M1: report creation flow complete; DRAFT_OFFLINE tested offline
- **Acceptance criteria:** Online: photo + location → API call → spinner → redirect to review; Offline: saved to IndexedDB → "Saved offline" message; no background sync attempted
- **Required tests:** Jest + RTL — online flow; offline fallback; retry

---

#### T4-7: AI review page — review, edit, approve complaint
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement citizen AI result review and complaint approval UI per Part A §15, §38 items 3,4.
- **Scope:**
  - Create `frontend/app/report/[id]/page.tsx`
  - Display: AI-detected category (with edit dropdown), AI-generated description (with edit textarea), AI-recommended authority (with override dropdown), confidence score, redacted image, duplicate warning if flagged
  - Editable fields: category (shadcn Select), description (shadcn Textarea), authority (shadcn Select)
  - "Submit Complaint" button → POST `/complaints/` then POST `/complaints/{id}/submit`
  - Show mock_gov_ref on success
  - Validation: Zod schema on all editable fields before submit
- **LOCKED decisions:** Part A §38 items 3,4 — citizen must approve all AI recommendations; no auto-submission
- **Dependencies:** T4-6, T3-4
- **Prerequisite tasks:** T4-6, T3-4
- **Complexity:** M
- **Blocking:** YES — complaint status page (T4-8) comes after
- **Parallelizable:** NO
- **Handoff:** M1: review page complete; all fields editable; mock_gov_ref displayed
- **Acceptance criteria:** AI results displayed; category/description/authority editable; submit creates complaint + shows mock_gov_ref; validation prevents empty submission
- **Required tests:** Jest + RTL — display AI results; edit fields; submit; validation errors

---

#### T4-8: Complaint detail and status timeline
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement complaint detail page with status timeline and Realtime subscription.
- **Scope:**
  - Create `frontend/app/report/[id]/page.tsx` (extends review page for existing complaints)
  - Fetch `GET /complaints/{id}` via SWR
  - Status timeline: visual steps (SUBMITTED → UNDER_REVIEW → RESOLVED/REJECTED)
  - Show redacted image (via signed URL)
  - Show mock_gov_ref
  - Show "File RTI" button if eligible (age ≥ 30 days AND status ≠ RESOLVED)
  - Supabase Realtime subscription: channel `complaints:{id}` → on status update → SWR revalidate → UI updates
- **LOCKED decisions:** Part A §15, §22, §24 — complaint lifecycle + Realtime
- **Dependencies:** T4-7, T3-7
- **Prerequisite tasks:** T4-7, T3-7
- **Complexity:** M
- **Blocking:** NO
- **Parallelizable:** YES — parallel with T4-9
- **Handoff:** M1: complaint detail + Realtime updates working; RTI button appears correctly
- **Acceptance criteria:** Status timeline renders correct active step; Realtime update → UI updates without refresh; RTI button visible/hidden based on eligibility
- **Required tests:** Jest + RTL — status display; RTI button eligibility; Realtime mock subscription

---

#### T4-9: RTI flow — draft review, edit, approve
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement RTI draft review/edit/approve flow per Part A §16.
- **Scope:**
  - Create `frontend/app/report/[id]/rti/page.tsx`
  - On load: POST `/rti/` (create RTI draft for complaint)
  - Display: AI-generated RTI letter draft (editable textarea)
  - "Approve and Submit RTI" button → POST `/rti/{id}/approve`
  - Show mock rti_ref on success
  - Status: show RTI status machine progression
- **LOCKED decisions:** Part A §16, §38 items 3,4 — citizen must approve RTI; mock submission only
- **Dependencies:** T4-8, T3-5
- **Prerequisite tasks:** T4-8, T3-5
- **Complexity:** M
- **Blocking:** NO
- **Parallelizable:** YES
- **Handoff:** M1: RTI flow complete; rti_ref displayed; status shown
- **Acceptance criteria:** RTI draft displayed; edit works; approve → rti_ref shown; ineligible complaint → error shown
- **Required tests:** Jest + RTL — draft display; edit; approve; ineligible error

---

#### T4-10: Admin screens
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement admin complaint management screens per Part A §5.
- **Scope:**
  - Create `frontend/app/admin/page.tsx` — admin-only route (middleware role check)
  - Complaints list: all complaints, paginated, filterable by status
  - Complaint detail: update status dropdown + confirm button
  - Resolve form: resolution notes + resolution photo upload
  - Redirect non-admin to dashboard
- **LOCKED decisions:** Part A §19 — admin role; Part A §5 — admin/ route
- **Dependencies:** T4-2, T3-6
- **Prerequisite tasks:** T4-2, T3-6
- **Complexity:** M
- **Blocking:** NO
- **Parallelizable:** YES
- **Handoff:** M1: admin screens working; role guard tested
- **Acceptance criteria:** Admin user → admin page accessible; citizen user → redirect to dashboard; status update works
- **Required tests:** Jest + RTL — admin role access; citizen redirect; status update

---

#### T4-11: PWA service worker and app shell caching
- **Phase:** 4
- **Owner:** M1 (primary), M5 (support)
- **Objective:** Configure next-pwa (serwist) for app shell caching and PWA manifest per Part A §17.
- **Scope:**
  - Install and configure `next-pwa` (serwist) in `next.config.js`
  - `public/manifest.json` — PWA manifest (name, icons, theme_color, display: standalone)
  - App shell routes cached: `/`, `/dashboard`, `/report/new`, `/login`
  - Service worker strategy: network-first for API calls; cache-first for app shell
  - No API response caching
- **LOCKED decisions:** Part A §17 — serwist; app shell cached; NO API response caching; NO background sync
- **Dependencies:** T4-6
- **Prerequisite tasks:** T4-6
- **Complexity:** S
- **Blocking:** NO — app works without PWA; PWA is enhancement
- **Parallelizable:** YES
- **Handoff:** M1 → M5: PWA manifest + service worker generated; tested on mobile
- **Acceptance criteria:** "Add to Home Screen" prompt appears; app shell loads offline; API calls fail gracefully offline; NO background sync registered
- **Required tests:** Lighthouse PWA audit; manual offline test

---

#### T4-12: IndexedDB offline draft storage
- **Phase:** 4
- **Owner:** M1 (primary)
- **Objective:** Implement idb-keyval draft storage for DRAFT_OFFLINE complaints per Part A §17.
- **Scope:**
  - Create `frontend/lib/offline-store.ts` using idb-keyval
  - `saveDraft(draft: DraftComplaint) → void` — save to IndexedDB with key = UUID
  - `listDrafts() → DraftComplaint[]` — list all pending drafts
  - `deleteDraft(id) → void` — remove after successful submission
  - Dashboard Pending Drafts section shows drafts; "Retry" button submits manually
  - Draft schema: `{id, image_blob, lat, lng, captured_at, status: "DRAFT_OFFLINE"}`
  - No automatic background retry (Part A §17)
- **LOCKED decisions:** Part A §17 — idb-keyval; IndexedDB; DRAFT_OFFLINE; manual retry only; NO background sync
- **Dependencies:** T4-6
- **Prerequisite tasks:** T4-6
- **Complexity:** S
- **Blocking:** NO
- **Parallelizable:** YES — parallel with T4-11
- **Handoff:** M1: offline-store.ts ready; dashboard pending drafts tested
- **Acceptance criteria:** Save draft offline → appears in dashboard; manual retry → submits when online; draft deleted after successful submission
- **Required tests:** Jest — save/list/delete draft; manual retry trigger

---

### Phase 4 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T4-1: API client + Supabase client connected; types compile
- [ ] T4-2: Login + register working; session context available
- [ ] T4-3: Dashboard renders complaint list + pending drafts
- [ ] T4-4: Camera captures photo; preview shown; blob returned
- [ ] T4-5: GPS acquired or manual MapLibre pin; location returned
- [ ] T4-6: Report creation flow: camera → GPS → API → AI spinner
- [ ] T4-7: AI review page: all fields editable; approve submits complaint
- [ ] T4-8: Complaint detail: status timeline; Realtime subscription active
- [ ] T4-9: RTI flow: draft shown; edit; approve; rti_ref displayed
- [ ] T4-10: Admin screens: role guard; status update works
- [ ] T4-11: PWA service worker: app shell cached; no background sync
- [ ] T4-12: IndexedDB drafts: save/list/delete; manual retry works

### Phase 4 Deliverables
- Complete Next.js frontend
- All citizen flows: report → review → submit → RTI
- Admin screens
- PWA with offline draft storage
- Realtime status updates

---

## Phase 5 — Security / Integration

### Objective
End-to-end security audit, integration testing, IDOR test suite,
cross-layer consistency checks, and accessibility/mobile validation.
All previous phases must be complete before Phase 5 begins.

### Entry Criteria
- Phases 1–4 all gates passed
- All API endpoints live
- Frontend connected to backend

### Phase 5 Tasks

---

#### T5-1: IDOR and RLS security test suite
- **Phase:** 5
- **Owner:** M4 (primary), M5 (support)
- **Objective:** Comprehensive automated test suite for IDOR and RLS policy violations.
- **Scope:**
  - pytest tests: citizen A cannot GET/PATCH/DELETE citizen B's reports, complaints, RTIs
  - Admin can access all; citizen cannot access admin endpoints
  - Authority officer can only access complaints assigned to their authority
  - Storage RLS: citizen A cannot download citizen B's images via signed URL manipulation
  - Raw Supabase client (bypassing API) must still enforce RLS
- **LOCKED decisions:** Part A §13, §19 — IDOR; RLS on all tables
- **Dependencies:** T3-1 through T3-7, T1-4, T1-6
- **Prerequisite tasks:** Phase 3 complete, Phase 1 complete
- **Complexity:** M
- **Blocking:** YES — security gate; no deployment until passing
- **Parallelizable:** NO
- **Handoff:** M4 → M5: security test suite passing; report to M2 for any fixes
- **Acceptance criteria:** All IDOR tests pass; all RLS tests pass; zero cross-user data leaks
- **Required tests:** pytest security suite (minimum 20 IDOR/RLS tests)

---

#### T5-2: Upload security tests
- **Phase:** 5
- **Owner:** M3 (primary), M5 (support)
- **Objective:** Verify all upload security controls per Part A §13, §28.
- **Scope:**
  - pytest: malformed MIME → 422; oversized file → 413; non-image → 422
  - Magic bytes check: JPEG magic bytes in PNG content-type → rejected
  - Pillow re-encode: EXIF data stripped; path traversal in filename → rejected
  - Malicious image (polyglot, zip bomb) → rejected by size or re-encode
- **LOCKED decisions:** Part A §13, §28 — upload security
- **Dependencies:** T2-2, T3-3
- **Prerequisite tasks:** T2-2, T3-3
- **Complexity:** S
- **Blocking:** YES
- **Parallelizable:** YES — parallel with T5-1
- **Handoff:** M3/M5 → M2: if any test fails, M2 fixes upload handler
- **Acceptance criteria:** All upload security tests pass; malicious inputs rejected before AI pipeline
- **Required tests:** pytest — 10+ upload security tests

---

#### T5-3: Prompt injection and LLM security tests
- **Phase:** 5
- **Owner:** M3 (primary), M5 (support)
- **Objective:** Verify prompt injection protection and LLM output validation per Part A §13.
- **Scope:**
  - pytest: inject `IGNORE PREVIOUS INSTRUCTIONS` in description field → sanitized before prompt
  - LLM output with invalid schema → fallback used; not passed to DB
  - LLM output with category not in taxonomy → rejected
  - Authority recommendation not in authority JSON → rejected
- **LOCKED decisions:** Part A §9 — prompt injection; output schema validation
- **Dependencies:** T2-8, T2-9, T2-10
- **Prerequisite tasks:** T2-8, T2-9, T2-10
- **Complexity:** S
- **Blocking:** YES
- **Parallelizable:** YES
- **Handoff:** M3/M5 → M3: if any test fails, M3 fixes sanitizer/validator
- **Acceptance criteria:** All prompt injection strings sanitized; all schema violations fall back to deterministic engine
- **Required tests:** pytest — 5+ injection tests; 5+ schema violation tests

---

#### T5-4: Frontend integration tests — Playwright E2E
- **Phase:** 5
- **Owner:** M1 (primary), M5 (support)
- **Objective:** Playwright E2E tests for all critical citizen flows.
- **Scope:**
  - Create `frontend/e2e/` Playwright tests:
    - `login.spec.ts` — login flow
    - `report-submit.spec.ts` — camera (mocked) → AI review → submit → mock_gov_ref visible
    - `rti-submit.spec.ts` — RTI flow for eligible complaint → approve → rti_ref visible
    - `admin-update.spec.ts` — admin login → update complaint status → Realtime update visible
    - `offline-draft.spec.ts` — go offline → fill form → save draft → go online → retry
- **LOCKED decisions:** Part A §27 — Playwright E2E
- **Dependencies:** Phase 4 complete
- **Prerequisite tasks:** Phase 4 complete
- **Complexity:** L
- **Blocking:** YES — E2E tests required before deployment
- **Parallelizable:** YES — parallel with T5-1, T5-2, T5-3
- **Handoff:** M1/M5: all E2E tests green on CI
- **Acceptance criteria:** All 5 E2E specs pass in CI; mobile viewport test passes
- **Required tests:** 5 Playwright spec files, minimum 20 total assertions

---

#### T5-5: Rate limiting and abuse prevention validation
- **Phase:** 5
- **Owner:** M2 (primary), M5 (support)
- **Objective:** Verify slowapi rate limits enforce correctly.
- **Scope:**
  - pytest: 11th AI endpoint request within 60s → 429
  - pytest: 61st standard endpoint request within 60s → 429
  - Verify rate limit resets after window
- **LOCKED decisions:** Part A §13 — slowapi; 10 req/min AI; 60 req/min standard
- **Dependencies:** T3-1
- **Prerequisite tasks:** T3-1
- **Complexity:** S
- **Blocking:** NO
- **Parallelizable:** YES
- **Handoff:** M2/M5: rate limit tests passing
- **Acceptance criteria:** Rate limits enforced; correct HTTP 429 returned with Retry-After header
- **Required tests:** pytest — AI rate limit, standard rate limit, reset after window

---

#### T5-6: Cross-layer consistency audit
- **Phase:** 5
- **Owner:** M4 (primary), all members
- **Objective:** Manual + automated cross-layer consistency checks per the consistency matrix.
- **Scope:**
  - DB schema ↔ Pydantic models: verify all fields match
  - API responses ↔ TypeScript types: verify all fields match
  - State machine in service layer ↔ DB enum values: verify all transitions match
  - Auth constraints ↔ RLS policies: verify they enforce the same rules
  - Authority JSON ↔ authority routing logic: verify all categories covered
  - Storage RLS ↔ API signed URL logic: verify consistent access patterns
- **LOCKED decisions:** All consistency checks listed in Part B introduction
- **Dependencies:** Phases 1–4 complete
- **Prerequisite tasks:** Phases 1–4 complete
- **Complexity:** M
- **Blocking:** YES — inconsistencies must be resolved before deployment
- **Parallelizable:** NO
- **Handoff:** M4 → all: audit report; identified gaps assigned to responsible owner
- **Acceptance criteria:** Zero schema/type mismatches; zero state machine gaps; all consistency checks documented as passing
- **Required tests:** Manual audit + automated schema comparison script

---

#### T5-7: Accessibility and mobile responsiveness
- **Phase:** 5
- **Owner:** M1 (primary)
- **Objective:** Verify WCAG 2.1 AA accessibility and mobile-first responsiveness on key pages.
- **Scope:**
  - Run axe-core accessibility scan on: login, dashboard, report/new, report/[id], RTI page
  - Fix any critical/serious violations
  - Mobile viewport (390px) test: all pages usable; no horizontal scroll; camera button accessible
  - Keyboard navigation: all interactive elements reachable
- **LOCKED decisions:** Part A §27 — accessibility; mobile responsiveness
- **Dependencies:** Phase 4 complete
- **Prerequisite tasks:** Phase 4 complete
- **Complexity:** M
- **Blocking:** NO — accessibility issues are quality issues, not blocking for demo
- **Parallelizable:** YES
- **Handoff:** M1: accessibility report; critical violations fixed
- **Acceptance criteria:** Zero critical/serious axe violations on key pages; mobile viewport renders correctly
- **Required tests:** axe-core scan; Playwright mobile viewport test

---

### Phase 5 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T5-1: All IDOR + RLS tests pass
- [ ] T5-2: All upload security tests pass
- [ ] T5-3: All prompt injection + LLM schema tests pass
- [ ] T5-4: All 5 Playwright E2E specs pass
- [ ] T5-5: Rate limiting enforced
- [ ] T5-6: Cross-layer consistency audit: zero gaps
- [ ] T5-7: Zero critical accessibility violations (non-blocking but tracked)

### Phase 5 Deliverables
- Full security test suite passing
- E2E tests green
- Cross-layer consistency verified
- Mobile-ready frontend

---

## Phase 6 — Deployment / Demo

### Objective
Deploy frontend to Vercel, backend to Render, configure keep-alive,
seed demo data, and execute hackathon demo dry run per Part A §32.

### Entry Criteria
- Phase 5 all blocking gates passed
- All environment variables prepared

### Phase 6 Tasks

---

#### T6-1: Backend deployment to Render
- **Phase:** 6
- **Owner:** M5 (primary), M2 (support)
- **Objective:** Deploy FastAPI backend to Render free web service.
- **Scope:**
  - Create Render web service pointing to `/backend` directory
  - Configure environment variables on Render: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `ALLOWED_ORIGINS`
  - Build command: `pip install -r requirements.txt`
  - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Verify `GET /health` returns 200 on Render URL
- **LOCKED decisions:** Part A §26 — Render free web service
- **Dependencies:** Phase 5 complete
- **Prerequisite tasks:** Phase 5 complete
- **Complexity:** S
- **Blocking:** YES
- **Parallelizable:** Parallel with T6-2
- **Handoff:** M5 → all: Render URL confirmed; /health live
- **Acceptance criteria:** `https://civicai-backend.onrender.com/health` → 200; env vars loaded; AI pipeline responds
- **Required tests:** Smoke test: POST /reports/ with test image from deployed URL

---

#### T6-2: Frontend deployment to Vercel
- **Phase:** 6
- **Owner:** M5 (primary), M1 (support)
- **Objective:** Deploy Next.js frontend to Vercel Hobby.
- **Scope:**
  - Connect GitHub repo to Vercel; set root directory to `/frontend`
  - Configure env vars on Vercel: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL`
  - Verify build passes; preview URL accessible
  - Configure production domain
- **LOCKED decisions:** Part A §26 — Vercel Hobby
- **Dependencies:** Phase 5 complete
- **Prerequisite tasks:** Phase 5 complete
- **Complexity:** S
- **Blocking:** YES
- **Parallelizable:** Parallel with T6-1
- **Handoff:** M5 → all: Vercel production URL confirmed
- **Acceptance criteria:** Production URL loads; login works; API calls reach Render backend
- **Required tests:** Smoke test: login → dashboard → report list

---

#### T6-3: Keep-alive cron job
- **Phase:** 6
- **Owner:** M5 (primary)
- **Objective:** Configure cron-job.org to prevent Render free tier sleep per Part A §26, §33.
- **Scope:**
  - Create cron-job.org job: GET `https://civicai-backend.onrender.com/health` every 14 minutes
  - Verify job is active
- **LOCKED decisions:** Part A §26 — cron-job.org; 14 min interval (Render sleeps at 15 min)
- **Dependencies:** T6-1
- **Prerequisite tasks:** T6-1
- **Complexity:** S
- **Blocking:** YES — Render cold start during demo is unacceptable
- **Parallelizable:** YES — parallel with T6-2, T6-4
- **Handoff:** M5 → all: cron job active; confirmed no cold starts after 30 min
- **Acceptance criteria:** Render backend responds in <2s (no cold start); cron-job.org shows successful pings
- **Required tests:** Manual: wait 20 min → request to backend → response time < 2s

---

#### T6-4: Demo data seeding
- **Phase:** 6
- **Owner:** M4 (primary), M5 (support)
- **Objective:** Seed Supabase with demo data for hackathon demo flow per Part A §32.
- **Scope:**
  - Create `supabase/seed/003_demo_data.sql`
  - Demo citizen account: citizen_demo@civicai.test (registered, profile created)
  - Demo admin account: admin_demo@civicai.test (role=admin)
  - Demo complaint: submitted 31 days ago (for RTI demo), status=UNDER_REVIEW
  - Demo complaint: recent, status=SUBMITTED (for normal demo flow)
  - RTI knowledge base seeded (T2-13 re-verified)
- **LOCKED decisions:** Part A §32, §40 item 3 — demo date manipulation via seed data
- **Dependencies:** T6-1, T1-8, T2-13
- **Prerequisite tasks:** T6-1, T1-8, T2-13
- **Complexity:** S
- **Blocking:** YES — demo flow requires seeded data
- **Parallelizable:** YES
- **Handoff:** M4 → all: demo credentials distributed; demo complaints visible in dashboard
- **Acceptance criteria:** Login as citizen_demo → 2 complaints visible; 31-day complaint shows RTI button
- **Required tests:** Manual: login → verify demo data present

---

#### T6-5: Deployment smoke test suite
- **Phase:** 6
- **Owner:** M5 (primary)
- **Objective:** Run smoke tests against production deployment.
- **Scope:**
  - pytest smoke test suite against production URLs:
    - `GET /health` → 200
    - Login → JWT returned
    - `POST /reports/` with test image → AI results returned
    - `POST /complaints/` → complaint created
    - `GET /complaints/` → list returned
    - `POST /rti/` on 31-day complaint → RTI draft returned
  - Playwright smoke: login → dashboard → report flow → RTI button visible
- **LOCKED decisions:** Part A §27 — deployment smoke tests
- **Dependencies:** T6-1, T6-2, T6-4
- **Prerequisite tasks:** T6-1, T6-2, T6-4
- **Complexity:** M
- **Blocking:** YES — final GO before demo
- **Parallelizable:** NO
- **Handoff:** M5 → all: smoke tests green; demo ready
- **Acceptance criteria:** All smoke tests pass against production; demo dry run completed per Part A §32
- **Required tests:** pytest smoke suite; Playwright smoke spec

---

#### T6-6: Demo dry run
- **Phase:** 6
- **Owner:** M5 (primary), all members present
- **Objective:** Execute full hackathon demo flow per Part A §32 end-to-end.
- **Scope:**
  - Follow demo script in Part A §32 step by step
  - Time the entire flow (target: < 5 minutes for core demo)
  - Test WiFi disable → DRAFT_OFFLINE → re-enable → manual retry
  - Confirm Realtime update visible on citizen screen when admin updates status
  - Note any issues → fix before presentation
- **LOCKED decisions:** Part A §32 — Hackathon Demo Flow
- **Dependencies:** T6-5
- **Prerequisite tasks:** T6-5
- **Complexity:** S
- **Blocking:** YES — final validation
- **Parallelizable:** NO
- **Handoff:** All members: demo sign-off; presentation ready
- **Acceptance criteria:** Full demo flow completes without errors; demo time < 5 minutes; all 13 demo steps in Part A §32 executed
- **Required tests:** Manual dry run

---

### Phase 6 Gate: GO / NO-GO

**GO criteria (all must pass):**
- [ ] T6-1: Backend live on Render; /health returns 200
- [ ] T6-2: Frontend live on Vercel; login works
- [ ] T6-3: Keep-alive active; no cold starts
- [ ] T6-4: Demo data seeded; demo accounts active
- [ ] T6-5: All smoke tests pass
- [ ] T6-6: Demo dry run completed per Part A §32 script

### Phase 6 Deliverables
- Production frontend on Vercel
- Production backend on Render
- Keep-alive active
- Demo data seeded
- Demo dry run signed off


---

## Dependency Graph

### Task-Level Dependencies (prerequisite → dependent)

```
None → T0-1
T0-1 → T0-2, T0-3, T0-4
T0-2 → T0-5, T4-1
T0-3 → T0-5, T2-1, T3-1
T0-4 → T1-1

T1-1 → T1-2
T1-2 → T1-3, T1-4
T1-3 → T2-12
T1-4 → T1-5, T1-6, T1-7, T1-8
T1-5 → T3-2
T1-6 → T2-2, T3-3
T1-8 → T3-1, T4-1

T2-1 → T2-2, T2-8
T2-2 → T2-3, T2-5, T2-7
T2-3 → T2-4
T2-4 → T2-11
T2-5 → T2-6, T2-11
T2-6 → T2-11
T2-7 → T2-11
T2-8 → T2-9
T2-9 → T2-10
T2-10 → T2-11, T3-5
T2-11 → T3-3
T2-12 → T2-13, T3-5
T2-13 → T6-4 (re-verify)

T3-1 → T3-2, T3-4, T3-5, T3-6, T3-7
T3-2 → T3-3
T3-3 → T3-4, T4-6
T3-4 → T3-5, T3-6, T3-7, T4-7
T3-5 → T4-9
T3-6 → T4-10
T3-7 → T4-8

T4-1 → T4-2
T4-2 → T4-3, T4-4, T4-5, T4-10
T4-4 → T4-6
T4-5 → T4-6
T4-6 → T4-7, T4-11, T4-12
T4-7 → T4-8
T4-8 → T4-9
T4-9, T4-10, T4-11, T4-12 → Phase 5

Phase 1+2+3+4 complete → T5-1, T5-2, T5-3, T5-4, T5-5, T5-6, T5-7
Phase 5 complete → T6-1, T6-2
T6-1 → T6-3, T6-4, T6-5
T6-2 → T6-5
T6-4 → T6-5
T6-5 → T6-6
```

---

## Critical Path

The critical path is the longest dependency chain that determines minimum project duration.

```
T0-1 (repo setup)
  → T0-4 (Supabase init)
    → T1-1 (enums)
      → T1-2 (tables)
        → T1-4 (RLS)
          → T1-6 (storage buckets)
          → T1-8 (auth + demo users)
            → T3-1 (auth middleware)
              → T3-2 (authority routing)
                → T3-3 (report service) ← also requires T2-11
                  → T3-4 (complaint service)
                    → T4-7 (AI review page)
                      → T4-8 (complaint detail + Realtime)
                        → T4-9 (RTI flow)
                          → Phase 5 (security/integration)
                            → T6-5 (smoke tests)
                              → T6-6 (demo dry run)

Also on critical path:
T0-3 → T2-1 → T2-2 → T2-3 → T2-4 → T2-11 → T3-3 (AI pipeline feeds into T3-3)
T0-2 → T4-1 → T4-2 → T4-4 + T4-5 → T4-6 → T4-7 (frontend chain feeds T4-7)
```

**Critical path summary:** T0-1 → T0-4 → T1-1 → T1-2 → T1-4 → T1-8 → T3-1 → T3-4 → T4-7 → T4-9 → T5-1 → T6-5 → T6-6

**Longest dependency chains that must not slip:**
1. Database foundation chain: T1-1 → T1-2 → T1-4 (must complete before backend can start)
2. AI pipeline chain: T2-1 → T2-2 → T2-3 → T2-4 → T2-11 (feeds report service)
3. Auth chain: T1-8 → T3-1 (feeds all authenticated routes)
4. Frontend chain: T4-1 → T4-2 → T4-4 → T4-6 → T4-7 (camera to complaint review)

---

## Parallel Workstreams

After Phase 0 completes, work can proceed in three parallel tracks after Phase 1:

### Workstream A: Database / Security (M4)
```
T1-1 → T1-2 → T1-3 (parallel with T1-4)
              → T1-4 → T1-5 (parallel with T1-6, T1-7, T1-8)
                      → Phase 5 security audit (T5-1, T5-6)
```

### Workstream B: AI / CV (M3) — starts after T0-3
```
T2-1 → T2-2 → T2-3 → T2-4 → T2-11 (sequential core pipeline)
       → T2-5 → T2-6 (parallel with T2-3 after T2-2)
       → T2-8 → T2-9 → T2-10 (parallel with T2-3 after T2-1)
       → T2-12 → T2-13 (parallel after T1-3 complete)
```

### Workstream C: Backend API (M2) — starts after Phase 1
```
T3-1 → T3-2 (parallel start)
T3-2 → T3-3 (requires T2-11 from Workstream B)
T3-3 → T3-4 → T3-5 (parallel with T3-6, T3-7)
```

### Workstream D: Frontend (M1) — starts after T0-2 for bootstrap, then waits for Phase 3 contracts
```
T4-1 → T4-2 → T4-3 (parallel with T4-4, T4-5)
T4-4 + T4-5 → T4-6 → T4-7 → T4-8 → T4-9
T4-10, T4-11, T4-12 (parallel after T4-6)
```

### Workstream E: DevOps / QA (M5)
```
T0-5 (CI/CD) — starts after T0-2, T0-3
Phase 5 testing (T5-4, T5-5) — parallel with T5-1 through T5-3
Phase 6 deployment (T6-1, T6-2, T6-3, T6-5, T6-6)
```

---

## CAN START IMMEDIATELY (after Phase 0 gate)
- T1-1 (M4): enums — starts day 1 of Phase 1
- T2-1 (M3): AI deps — starts day 1; independent of Phase 1

## CAN RUN IN PARALLEL (within Phase 1)
- T1-3 ‖ T1-4 (after T1-2)
- T1-5 ‖ T1-6 ‖ T1-7 (after T1-4)
- T1-7 ‖ T1-8 (after T1-4)

## CAN RUN IN PARALLEL (after Phase 1)
- Phase 2 workstream (M3) ‖ Phase 3 non-AI tasks (M2) ‖ Phase 4 bootstrap (M1)
- T2-5 ‖ T2-3/T2-4 (after T2-2)
- T2-8 ‖ T2-5 (after T2-1)
- T3-5 ‖ T3-6 ‖ T3-7 (after T3-4)
- T4-3 ‖ T4-4 ‖ T4-5 (after T4-2)
- T4-11 ‖ T4-12 (after T4-6)

## MUST WAIT FOR
- T3-3: must wait for T2-11 (AI pipeline complete)
- T4-7: must wait for T3-4 (complaint service complete)
- T4-9: must wait for T3-5 (RTI service complete)
- Phase 5: must wait for all of Phases 1–4
- Phase 6: must wait for Phase 5 blocking gates

---

## Integration Points

| Integration | Task A | Task B | Description |
|-------------|--------|--------|-------------|
| AI → Report Service | T2-11 | T3-3 | `run_ai_pipeline()` called from `report_service.py` |
| Report → Complaint | T3-3 | T3-4 | report_id FK; complaint created from approved report |
| Complaint → RTI | T3-4 | T3-5 | complaint_id FK; RTI eligibility checks complaint status |
| LLM → RTI Draft | T2-10 | T3-5 | `generate_rti_draft()` called from `rti_service.py` |
| RAG → RTI | T2-12 | T3-5 | `retrieve_context()` called from `rti_service.py` |
| Auth → All Routes | T1-8 | T3-1 | JWT from Supabase Auth verified by FastAPI dependency |
| Realtime → Frontend | T3-7 | T4-8 | Supabase Realtime channel subscribed in complaint detail page |
| Storage → Signed URLs | T1-6 | T3-3 | Storage client generates signed URLs in report service |
| RLS → API | T1-4 | T3-1 | RLS enforces DB-level isolation; API enforces IDOR at service layer |
| Authority JSON → Router | T1-5 | T3-2 | JSON loaded at startup; router called from report service |
| Frontend → API | T4-1 | T3-1 | API client attaches JWT; API verifies JWT |

---

## Blocking Tasks Summary

| Task | Blocks |
|------|--------|
| T0-1 | Everything |
| T0-2 | All frontend tasks |
| T0-3 | All backend + AI tasks |
| T0-4 | All database tasks |
| T1-1 | T1-2 and all downstream |
| T1-2 | T1-3, T1-4 and all downstream |
| T1-4 | T1-5, T1-6, T1-7, T1-8 |
| T1-6 | T2-2 (storage), T3-3 (upload) |
| T1-8 | T3-1 (auth), T4-1 (frontend auth) |
| T2-11 | T3-3 (report service) |
| T3-1 | All authenticated API routes |
| T3-3 | T3-4 (complaints) |
| T3-4 | T3-5, T3-6, T3-7 |
| T4-2 | All authenticated frontend pages |
| T5-1 | Deployment (security gate) |
| T5-4 | Deployment (E2E gate) |
| T5-6 | Deployment (consistency gate) |
| T6-5 | T6-6 (demo dry run) |

---

## Required Handoffs Between Owners

| From | To | Task | Handoff Content |
|------|----|------|----------------|
| M4 | M1, M2 | T1-8 | Demo user credentials; JWT sample |
| M4 | M2, M3 | T1-5 | authorities.json path; seed row count |
| M4 | M2, M3 | T1-4 | RLS policies active; IDOR test matrix |
| M3 | M2 | T2-11 | `run_ai_pipeline()` API; AIResult schema; test fixtures |
| M3 | M2 | T2-12 | `retrieve_context()` API; RAM gate behavior |
| M2 | M1 | T3-3 | POST /reports/ API contract; response schema |
| M2 | M1 | T3-4 | Complaint API contract; state machine transitions |
| M2 | M1 | T3-5 | RTI API contract; rti_ref format |
| M2 | M1 | T3-7 | Realtime channel name; event schema |
| M1 | M5 | T4-11 | PWA manifest; service worker config |
| M4 | M5 | T5-1 | Security test suite results |
| M5 | All | T6-1 | Render URL; /health confirmed |
| M5 | All | T6-2 | Vercel production URL |
| M5 | All | T6-5 | Smoke tests green; demo ready |


---

## File-by-File Build Map

| Repository Path | Purpose | Created by Task | Primary Owner | Dependencies |
|-----------------|---------|-----------------|---------------|--------------|
| `README.md` | Project overview | T0-1 | M5 | None |
| `.gitignore` | Ignore env/build files | T0-1 | M5 | None |
| `.github/workflows/ci.yml` | PR lint+test CI | T0-5 | M5 | T0-2, T0-3 |
| `.github/workflows/deploy.yml` | Deploy on merge | T0-5 | M5 | T0-2, T0-3 |
| `docs/CIVICAI_MASTER_ARCHITECTURE.md` | LOCKED architecture | Pre-existing | — | — |
| `docs/CIVICAI_MASTER_ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md` | This document | T0-1 | — | — |
| **Supabase** | | | | |
| `supabase/migrations/001_enums.sql` | DB enums | T1-1 | M4 | T0-4 |
| `supabase/migrations/002_tables.sql` | Core tables | T1-2 | M4 | T1-1 |
| `supabase/migrations/003_indexes.sql` | Performance indexes | T1-3 | M4 | T1-2 |
| `supabase/migrations/004_rls.sql` | RLS policies | T1-4 | M4 | T1-2 |
| `supabase/migrations/005_audit_trigger.sql` | Audit log trigger | T1-7 | M4 | T1-2, T1-4 |
| `supabase/migrations/006_auth_trigger.sql` | Profile auto-create | T1-8 | M4 | T1-2, T1-4 |
| `supabase/seed/001_authorities.sql` | Authority seed data | T1-5 | M4 | T1-4 |
| `supabase/seed/002_rti_knowledge_base.sql` | RTI knowledge chunks | T2-13 | M3 | T2-12, T1-2 |
| `supabase/seed/003_demo_data.sql` | Hackathon demo data | T6-4 | M4 | T1-8, T2-13 |
| **Backend — root** | | | | |
| `backend/requirements.txt` | Python dependencies | T0-3 + T2-1 | M2+M3 | T0-1 |
| `backend/main.py` | FastAPI app factory | T0-3 | M2 | T0-1 |
| `backend/config.py` | Pydantic Settings | T0-3 | M2 | T0-1 |
| `backend/dependencies.py` | Shared FastAPI deps | T3-1 | M2 | T1-8 |
| `backend/.env.example` | Env var template | T0-3 | M2 | T0-1 |
| **Backend — routers** | | | | |
| `backend/routers/health.py` | GET /health | T0-3 | M2 | T0-1 |
| `backend/routers/reports.py` | POST/GET /reports/ | T3-3 | M2 | T3-2, T2-11 |
| `backend/routers/complaints.py` | Complaint endpoints | T3-4 | M2 | T3-3 |
| `backend/routers/rti.py` | RTI endpoints | T3-5 | M2 | T3-4 |
| `backend/routers/admin.py` | Admin endpoints | T3-6 | M2 | T3-4 |
| **Backend — services** | | | | |
| `backend/services/report_service.py` | Report workflow | T3-3 | M2 | T2-11, T3-2 |
| `backend/services/complaint_service.py` | Complaint workflow | T3-4 | M2 | T3-3 |
| `backend/services/rti_service.py` | RTI workflow | T3-5 | M2 | T3-4, T2-12 |
| `backend/services/ai_service.py` | AI orchestration shim | T3-3 | M2 | T2-11 |
| `backend/services/llm_service.py` | LLM provider selector | T2-10 | M3 | T2-8, T2-9 |
| `backend/services/rag_service.py` | RAG context builder | T2-12 | M3 | T2-12 |
| `backend/services/authority_service.py` | Authority routing | T3-2 | M2 | T1-5 |
| `backend/services/storage_service.py` | Signed URL management | T3-3 | M2 | T1-6 |
| `backend/services/realtime_service.py` | Realtime publish | T3-7 | M2 | T3-4 |
| **Backend — CV** | | | | |
| `backend/cv/ram_check.py` | RAM availability check | T2-1 | M3 | T0-3 |
| `backend/cv/image_validator.py` | Image MIME/size/magic | T2-2 | M3 | T2-1 |
| `backend/cv/privacy.py` | Face + plate redaction | T2-3, T2-4 | M3 | T2-2 |
| `backend/cv/detection.py` | YOLOv8n inference | T2-5 | M3 | T2-2 |
| `backend/cv/taxonomy.py` | YOLO → civic category | T2-5 | M3 | T2-5 |
| `backend/cv/confidence.py` | Evidence confidence | T2-6 | M3 | T2-5 |
| `backend/cv/pipeline.py` | Master AI pipeline | T2-11 | M3 | T2-3..T2-10 |
| **Backend — LLM** | | | | |
| `backend/llm/prompts.py` | Prompt templates | T2-8 | M3 | T2-1 |
| `backend/llm/groq_provider.py` | Groq API integration | T2-8 | M3 | T2-1 |
| `backend/llm/output_validator.py` | LLM schema validation | T2-8 | M3 | T2-8 |
| `backend/llm/fallback_provider.py` | Deterministic fallback | T2-9 | M3 | T2-8 |
| `backend/llm/watsonx_stub.py` | IBM Watsonx stub | T2-9 | M3 | T2-9 |
| **Backend — RAG** | | | | |
| `backend/rag/embedder.py` | BAAI embedding + RAM gate | T2-12 | M3 | T2-1, T1-3 |
| `backend/rag/vector_store.py` | pgvector queries | T2-12 | M3 | T1-3 |
| `backend/rag/chunker.py` | Document chunking | T2-13 | M3 | T2-12 |
| `backend/rag/retriever.py` | Semantic + keyword search | T2-12 | M3 | T2-12 |
| **Backend — DB** | | | | |
| `backend/db/supabase_client.py` | Supabase service client | T3-1 | M2 | T0-4 |
| `backend/db/repositories/report_repo.py` | Report DB access | T3-3 | M2 | T1-2 |
| `backend/db/repositories/complaint_repo.py` | Complaint DB access | T3-4 | M2 | T1-2 |
| `backend/db/repositories/rti_repo.py` | RTI DB access | T3-5 | M2 | T1-2 |
| `backend/db/repositories/authority_repo.py` | Authority JSON access | T3-2 | M2 | T1-5 |
| **Backend — Security** | | | | |
| `backend/security/jwt_verify.py` | JWT RS256 verify | T3-1 | M2 | T1-8 |
| `backend/security/rbac.py` | Role-based access control | T3-1 | M2 | T3-1 |
| `backend/security/ownership.py` | IDOR ownership check | T3-1 | M2 | T3-1 |
| `backend/security/input_sanitizer.py` | Prompt injection guard | T3-1 | M2 | T3-1 |
| **Backend — Data** | | | | |
| `backend/data/mangaluru_authorities.json` | IMMUTABLE authority data | T1-5 | M4 | T0-1 |
| **Frontend — root** | | | | |
| `frontend/package.json` | NPM dependencies | T0-2 | M1 | T0-1 |
| `frontend/next.config.js` | Next.js config + PWA | T0-2, T4-11 | M1 | T0-2 |
| `frontend/tsconfig.json` | TypeScript config | T0-2 | M1 | T0-2 |
| `frontend/.env.local.example` | Frontend env template | T0-2 | M1 | T0-2 |
| `frontend/middleware.ts` | Auth redirect middleware | T4-2 | M1 | T4-1 |
| `frontend/public/manifest.json` | PWA manifest | T4-11 | M1 | T0-2 |
| **Frontend — lib** | | | | |
| `frontend/lib/supabase.ts` | Supabase browser client | T4-1 | M1 | T0-2, T1-8 |
| `frontend/lib/api-client.ts` | FastAPI typed client | T4-1 | M1 | T3-1 |
| `frontend/lib/types.ts` | TypeScript types | T4-1 | M1 | T3-1 |
| `frontend/lib/auth-context.tsx` | Auth React Context | T4-2 | M1 | T4-1 |
| `frontend/lib/offline-store.ts` | IndexedDB draft storage | T4-12 | M1 | T4-6 |
| **Frontend — app pages** | | | | |
| `frontend/app/layout.tsx` | Root layout | T0-2 | M1 | T0-2 |
| `frontend/app/(auth)/login/page.tsx` | Login page | T4-2 | M1 | T4-1 |
| `frontend/app/(auth)/register/page.tsx` | Register page | T4-2 | M1 | T4-1 |
| `frontend/app/dashboard/page.tsx` | Complaint dashboard | T4-3 | M1 | T4-2 |
| `frontend/app/report/new/page.tsx` | Report creation flow | T4-6 | M1 | T4-4, T4-5 |
| `frontend/app/report/[id]/page.tsx` | AI review + complaint detail | T4-7, T4-8 | M1 | T4-6 |
| `frontend/app/report/[id]/rti/page.tsx` | RTI flow | T4-9 | M1 | T4-8 |
| `frontend/app/admin/page.tsx` | Admin complaints | T4-10 | M1 | T4-2 |
| **Frontend — components** | | | | |
| `frontend/components/camera/CameraCapture.tsx` | Camera capture | T4-4 | M1 | T4-2 |
| `frontend/components/map/LocationPicker.tsx` | GPS + MapLibre pin | T4-5 | M1 | T4-2 |
| **Frontend — E2E tests** | | | | |
| `frontend/e2e/login.spec.ts` | Login E2E | T5-4 | M1+M5 | T4-2 |
| `frontend/e2e/report-submit.spec.ts` | Report E2E | T5-4 | M1+M5 | T4-7 |
| `frontend/e2e/rti-submit.spec.ts` | RTI E2E | T5-4 | M1+M5 | T4-9 |
| `frontend/e2e/admin-update.spec.ts` | Admin E2E | T5-4 | M1+M5 | T4-10 |
| `frontend/e2e/offline-draft.spec.ts` | Offline E2E | T5-4 | M1+M5 | T4-12 |

---

## Database Implementation Plan

### Extensions (T0-4)
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Enums (T1-1 → `001_enums.sql`)
```sql
CREATE TYPE complaint_status AS ENUM (
  'DRAFT','SUBMITTED','UNDER_REVIEW','RESOLVED','REJECTED','ARCHIVED'
);
CREATE TYPE rti_status AS ENUM (
  'DRAFT','SUBMITTED','ACKNOWLEDGED','RESPONDED','ESCALATED','CLOSED'
);
CREATE TYPE issue_category AS ENUM (
  'pothole','waterlogging','broken_streetlight','garbage_overflow',
  'open_drain','illegal_construction','water_supply','sewage','road_damage','other'
);
CREATE TYPE user_role AS ENUM ('citizen','admin','authority_officer');
```

### Tables (T1-2 → `002_tables.sql`)
```sql
-- profiles: extends auth.users
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  phone TEXT,
  role user_role NOT NULL DEFAULT 'citizen',
  ward_number INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- authorities: seeded from immutable JSON
-- ADR-001: no ward geometry, no ward range integers; routing uses category + area_text only
CREATE TABLE authorities (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  jurisdiction TEXT,
  categories issue_category[] NOT NULL,
  area_text TEXT,
  contact_email TEXT,
  phone TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- reports: raw report before complaint creation
CREATE TABLE reports (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id),
  image_original_path TEXT NOT NULL,
  image_redacted_path TEXT,
  image_hash TEXT NOT NULL,
  location GEOGRAPHY(POINT, 4326),
  address_text TEXT,
  ai_category issue_category,
  ai_confidence FLOAT,
  ai_authority_id UUID REFERENCES authorities(id),
  ai_raw_response JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- complaints: citizen-approved complaint
CREATE TABLE complaints (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_id UUID UNIQUE REFERENCES reports(id),
  user_id UUID NOT NULL REFERENCES profiles(id),
  category issue_category NOT NULL,
  description TEXT NOT NULL,
  authority_id UUID NOT NULL REFERENCES authorities(id),
  status complaint_status NOT NULL DEFAULT 'DRAFT',
  submitted_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  resolution_image_path TEXT,
  resolution_notes TEXT,
  mock_gov_ref TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- rti_requests: RTI for stale complaints
CREATE TABLE rti_requests (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  complaint_id UUID UNIQUE NOT NULL REFERENCES complaints(id),
  user_id UUID NOT NULL REFERENCES profiles(id),
  status rti_status NOT NULL DEFAULT 'DRAFT',
  draft_text TEXT,
  approved_text TEXT,
  mock_submitted_at TIMESTAMPTZ,
  rti_ref TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- rti_knowledge_base: RAG content
CREATE TABLE rti_knowledge_base (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1536),
  source_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- audit_log: immutable append-only
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES profiles(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id UUID NOT NULL,
  metadata JSONB,
  ip_address INET,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Indexes (T1-3 → `003_indexes.sql`)
```sql
CREATE INDEX idx_reports_location ON reports USING GIST (location);
CREATE INDEX idx_complaints_user_status ON complaints (user_id, status);
CREATE INDEX idx_complaints_authority ON complaints (authority_id);
CREATE INDEX idx_audit_log_user ON audit_log (user_id);
CREATE INDEX idx_audit_log_entity ON audit_log (entity_id);
CREATE INDEX idx_rti_kb_embedding ON rti_knowledge_base
  USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);
```

### RLS Policies (T1-4 → `004_rls.sql`)
- All tables: `ALTER TABLE <name> ENABLE ROW LEVEL SECURITY;`
- `profiles`: SELECT WHERE id = auth.uid(); INSERT WHERE id = auth.uid()
- `reports`: citizen SELECT/INSERT WHERE user_id = auth.uid(); admin SELECT all
- `complaints`: citizen SELECT/INSERT WHERE user_id = auth.uid(); admin SELECT/UPDATE all
- `rti_requests`: citizen SELECT/INSERT WHERE user_id = auth.uid(); admin SELECT all
- `rti_knowledge_base`: authenticated SELECT; service role INSERT only
- `audit_log`: service role INSERT; citizen SELECT WHERE user_id = auth.uid(); admin SELECT all

### Audit Trigger (T1-7 → `005_audit_trigger.sql`)
```sql
CREATE OR REPLACE FUNCTION log_status_change()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO audit_log (user_id, action, entity_type, entity_id, metadata)
  VALUES (
    auth.uid(),
    TG_OP,
    TG_TABLE_NAME,
    NEW.id,
    jsonb_build_object('old_status', OLD.status, 'new_status', NEW.status)
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER complaints_audit AFTER INSERT OR UPDATE OF status ON complaints
  FOR EACH ROW EXECUTE FUNCTION log_status_change();
CREATE TRIGGER rti_audit AFTER UPDATE OF status ON rti_requests
  FOR EACH ROW EXECUTE FUNCTION log_status_change();
```

### Auth Profile Trigger (T1-8 → `006_auth_trigger.sql`)
```sql
CREATE OR REPLACE FUNCTION create_profile_on_register()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, full_name)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION create_profile_on_register();
```

### Storage Buckets (T1-6)
```
Bucket: report-originals   — private; owner+admin read; service write
Bucket: report-redacted     — private; owner+admin+authority_officer(assigned) read; service write
Bucket: resolution-photos   — private; owner read; admin+service write
Bucket: rti-documents       — private; owner read/write; admin read
```

---

## Backend Implementation Plan

### Bootstrap (T0-3)
- `main.py`: create FastAPI app; add CORS middleware (ALLOWED_ORIGINS); register all routers; add rate limiter to state
- `config.py`: Pydantic BaseSettings; fields: SUPABASE_URL, SUPABASE_SERVICE_KEY, GROQ_API_KEY, ALLOWED_ORIGINS, ENV

### Security Layer (T3-1)
- `jwt_verify.py`: use `python-jose` to decode Supabase JWT; fetch Supabase JWKS for RS256 verification; extract `sub` as user_id and `role` from profile
- `rbac.py`: `require_role(roles: list[UserRole])` → raises 403 if user role not in list
- `ownership.py`: `assert_owns(entity_user_id, current_user)` → raises 403 if mismatch; admin bypasses
- `input_sanitizer.py`: strip `\r\n`, HTML tags, LLM injection patterns from text; limit to 2000 chars

### Service Layer Rules (Part A §6 — enforced)
- Route handlers: receive request → validate → call service → return response schema
- Services: contain all business logic, DB calls, external API calls
- Repositories: contain only DB queries; no business logic
- No raw SQL string interpolation; use Supabase client parameterized methods

### Report Workflow (T3-3)
```
POST /reports/ receives: multipart/form-data (image file + lat + lng)
  1. auth dependency: verify JWT → get current_user
  2. rate_limit: 10/min AI endpoint
  3. report_service.create_report():
     a. image_validator.validate(image_bytes)
     b. cv/pipeline.run_ai_pipeline(image_bytes, location)
     c. storage_service.upload_original(original_bytes) → path
     d. storage_service.upload_redacted(redacted_bytes) → path
     e. report_repo.insert(user_id, paths, ai_result, location)
     f. return ReportResponse with signed URLs + AI results
```

### Complaint Workflow (T3-4)
```
POST /complaints/ — create complaint (DRAFT status)
POST /complaints/{id}/submit:
  1. complaint_service.submit_complaint():
     a. assert_owns(complaint.user_id, current_user)
     b. validate state: DRAFT → SUBMITTED only
     c. mock_gov_ref = f"MCC-{uuid4().hex[:8].upper()}"
     d. complaint_repo.update(status=SUBMITTED, mock_gov_ref, submitted_at=NOW)
     e. realtime_service.publish(complaint_id, SUBMITTED)
     f. audit_log INSERT (via trigger)
```

### Mock Government Submission (T3-4)
- `mock_gov_ref` is generated server-side: `f"MCC-{uuid4().hex[:8].upper()}"`
- No HTTP call to any external service
- Stored in `complaints.mock_gov_ref`
- Displayed to citizen as "Your complaint reference number"

### RTI Eligibility Check (T3-5)
```python
def check_eligibility(complaint_id, user_id):
  complaint = complaint_repo.get(complaint_id)
  assert_owns(complaint.user_id, user_id)
  if complaint.status == 'RESOLVED':
    raise RTIIneligibleError("Complaint already resolved")
  if (NOW - complaint.submitted_at).days < 30:
    raise RTIIneligibleError("Complaint less than 30 days old")
  if rti_repo.exists_for_complaint(complaint_id):
    raise RTIIneligibleError("RTI already filed")
  return True
```

### API Response Envelope (all routes)
```python
class APIResponse(BaseModel):
    data: Any | None
    error: ErrorDetail | None = None

class ErrorDetail(BaseModel):
    code: str
    message: str
```

---

## AI/CV Implementation Plan

### RAM Strategy (LOCKED — Part A §8)
```
At process startup: NO models loaded
On first image request:
  1. Load YuNet ONNX (~5 MB) → stays resident
  2. Load fast-alpr (~80 MB) → stays resident
  3. Load YOLOv8n (~30 MB) → stays resident
  Total resident: ~115 MB

BAAI loading decision (separate check):
  if psutil.virtual_memory().available > 512 * 1024 * 1024:
    load BAAI (~440 MB)
    EMBEDDING_ENABLED = True
  else:
    EMBEDDING_ENABLED = False  # keyword RAG fallback

Models are loaded lazily using module-level singleton pattern.
Memory cleanup after pipeline: gc.collect() but do NOT unload CV models.
```

### Lazy Model Singleton Pattern
```python
# In each model module:
_model = None

def get_model():
    global _model
    if _model is None:
        _model = load_model()
    return _model
```

### Image Validation (T2-2)
- MIME types accepted: `image/jpeg`, `image/png`, `image/webp`
- Magic bytes: JPEG = `FF D8 FF`; PNG = `89 50 4E 47`; WebP = `52 49 46 46`
- Max size: 10 MB (10 * 1024 * 1024 bytes)
- Min dimensions: 200×200 px
- Pillow re-encode: `img.save(buffer, format='JPEG', quality=85)` — strips EXIF, normalizes format
- Resize: `img.thumbnail((1024, 1024), Image.LANCZOS)` — reduces CV inference memory

### Privacy Pipeline (T2-3, T2-4)
```python
def redact_privacy(image: PIL.Image) -> PIL.Image:
    img = redact_faces(image)   # YuNet
    img = redact_plates(img)    # fast-alpr
    return img
```
- Face redaction: detect → `ImageFilter.GaussianBlur(radius=20)` on each bounding box
- Plate redaction: detect → `ImageDraw.rectangle(bbox, fill=(0,0,0))` on each bounding box
- Both: if no detections → return image unchanged

### YOLO Pipeline (T2-5)
- Model: `ultralytics.YOLO('yolov8n.pt')` — CPU mode
- Inference: `model(image_array, verbose=False)` → `results[0].boxes`
- Top-1 class: `max(results[0].boxes, key=lambda b: b.conf)[0]`
- Return: `{yolo_class: str, confidence: float, bbox: list[int]}`

### Taxonomy Mapping (T2-5)
```python
YOLO_TO_CATEGORY = {
    # Map common YOLO COCO classes to civic issue categories
    # (actual mapping depends on training data; defaults to 'other' for unknown)
    "pothole": "pothole",
    "water": "waterlogging",
    # ... etc
}
```

### LLM Prompt Construction (T2-8)
```
COMPLAINT_DESCRIPTION_PROMPT = """
You are a civic complaint assistant for Mangaluru, India.
Given the following information, generate a clear complaint description.

Category: {category}
Location: {address}
Evidence confidence: {confidence:.0%}
Detected objects: {detected_objects}

Generate a complaint description in 2-3 sentences.
Do not invent information not present above.
Return JSON: {{"description": "...", "category": "...", "confidence": 0.0}}
"""
```

### Prompt Injection Protection (T2-8, T3-1)
```python
INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt",
    r"\bforget\b.{0,20}\binstructions\b",
    r"<\|.*?\|>",  # special tokens
]

def sanitize_for_prompt(text: str) -> str:
    for pattern in INJECTION_PATTERNS:
        text = re.sub(pattern, "[removed]", text, flags=re.IGNORECASE)
    return text[:2000]  # hard length limit
```

### LLM Output Validation (T2-8)
```python
class LLMOutput(BaseModel):
    category: IssueCategory
    description: str = Field(max_length=500)
    authority_recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)

def validate_output(raw: dict) -> LLMOutput:
    try:
        return LLMOutput(**raw)
    except ValidationError:
        raise LLMOutputInvalid()
    # Caller catches LLMOutputInvalid → falls back to deterministic
```

---

## RTI/RAG Implementation Plan

### Knowledge Base Content (T2-13)
Content categories to include:
1. RTI Act 2005 — key sections: Section 6 (application), Section 7 (timeline), Section 19 (appeal)
2. Mangaluru City Corporation complaint procedure summary
3. Karnataka Municipal Corporations Act relevant provisions
4. Sample RTI letter format
5. BBMP/MCC contact hierarchy for escalation

### Chunking Strategy (T2-13)
```python
def chunk_document(text: str, max_tokens: int = 512) -> list[str]:
    # Split on sentence boundaries; accumulate until token limit
    # Use tiktoken for token counting
    chunks = []
    current_chunk = []
    current_tokens = 0
    for sentence in split_sentences(text):
        tokens = count_tokens(sentence)
        if current_tokens + tokens > max_tokens:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_tokens = tokens
        else:
            current_chunk.append(sentence)
            current_tokens += tokens
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks
```

### Vector Search (T2-12)
```sql
SELECT id, title, content,
       1 - (embedding <=> $1::vector) AS similarity
FROM rti_knowledge_base
WHERE embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT 5;
```

### Keyword Fallback (T2-12)
```sql
SELECT id, title, content
FROM rti_knowledge_base
WHERE content ILIKE '%' || $1 || '%'
   OR title ILIKE '%' || $1 || '%'
LIMIT 5;
```

### RTI Draft Prompt
```
RTI_DRAFT_PROMPT = """
You are drafting an RTI (Right to Information) application under the RTI Act 2005.

Complaint details:
- Category: {category}
- Location: {address}
- Submitted: {submitted_at}
- Authority: {authority_name}
- Reference: {mock_gov_ref}
- Status: {status} (no resolution for {days_elapsed} days)

Relevant RTI context:
{rag_context}

Draft a formal RTI application addressing:
1. Information sought about complaint status
2. Actions taken by authority
3. Timeline of events

Format as a formal letter. Max 500 words.
Return JSON: {{"draft_text": "..."}}
"""
```

### Embedding-Unavailable Fallback
When `EMBEDDING_ENABLED = False`:
- `retriever.py` calls keyword fallback directly (no embedding computed)
- LLM draft still works; context quality is lower but draft is still generated
- Frontend shows no special message (invisible degradation)

---

## Frontend Implementation Plan

### Global Error and Loading Handling
- Create `frontend/components/ui/ErrorBoundary.tsx` — React error boundary for page-level errors
- SWR config: global `onError` handler → show toast notification
- API client: network error → catch → show "Connection error. Please check your connection." message

### Form Validation Pattern (all forms use Zod + react-hook-form)
```typescript
const schema = z.object({
  category: z.enum(ISSUE_CATEGORIES),
  description: z.string().min(10).max(500),
  authority_id: z.string().uuid()
})

const form = useForm<z.infer<typeof schema>>({
  resolver: zodResolver(schema)
})
```

### Camera Capture Implementation (T4-4)
```typescript
// Use rear camera; fall back to any camera
const stream = await navigator.mediaDevices.getUserMedia({
  video: { facingMode: { ideal: 'environment' } }
})
// Show live preview in <video> element
// On capture: draw to <canvas> → toBlob('image/jpeg', 0.85)
// On error: show error message — NO file input fallback
```

### Offline Detection and DRAFT_OFFLINE Flow (T4-12)
```typescript
// In report creation page:
const handleSubmit = async (data) => {
  if (!navigator.onLine) {
    await saveDraft({ ...data, status: 'DRAFT_OFFLINE', id: uuid() })
    showMessage("Saved offline. Tap 'Retry' from dashboard when connected.")
    return
  }
  // proceed with API call
}

// Dashboard pending drafts:
const drafts = await listDrafts()
// Render each draft with "Retry" button
// On Retry click: attempt API call → on success: deleteDraft(id)
// NO automatic retry, NO background sync
```

### Realtime Subscription (T4-8)
```typescript
// In complaint detail page:
useEffect(() => {
  const channel = supabase
    .channel(`complaints:${complaintId}`)
    .on('broadcast', { event: 'status_update' }, () => {
      mutate() // SWR revalidate
    })
    .subscribe()
  return () => { supabase.removeChannel(channel) }
}, [complaintId])
```

### MapLibre Integration (T4-5)
```typescript
// Initialize with Mangaluru viewport
const map = new maplibregl.Map({
  container: mapRef.current,
  style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [74.856, 12.914],  // Mangaluru
  zoom: 12
})

// Add marker on GPS or manual click
map.on('click', (e) => {
  setLocation({ lat: e.lngLat.lat, lng: e.lngLat.lng })
  marker.setLngLat(e.lngLat)
})
```

---

## Security Implementation Plan

### Security Requirement → Task Mapping

| Security Requirement | Implementation Task | Test Task |
|----------------------|--------------------|-----------| 
| JWT RS256 verification | T3-1 (jwt_verify.py) | T3-1 tests + T5-1 |
| RBAC — 3 roles | T3-1 (rbac.py) | T3-1 tests + T5-1 |
| IDOR ownership checks | T3-1 (ownership.py) | T5-1 |
| Input validation (API) | T3-1 (input_sanitizer.py) + Pydantic | T5-3 |
| Input validation (Frontend) | T4-7 (Zod schemas) | T5-4 E2E |
| SQL injection resistance | All repos (Supabase client) | T5-1 (raw client test) |
| XSS prevention | Next.js JSX + JSON-only API | T5-4 E2E |
| CORS restriction | T3-1 (main.py CORS) | T5-5 |
| Upload MIME/magic bytes | T2-2 (image_validator.py) | T5-2 |
| Pillow re-encode (strip EXIF) | T2-2 | T5-2 |
| Malicious image handling | T2-2 (size + re-encode) | T5-2 |
| Path traversal prevention | Storage UUID-only paths (T3-3) | T5-2 |
| Signed URL expiry | T3-3 (storage_service.py) | T5-1 |
| Storage RLS | T1-6 (004_rls.sql) | T5-1 |
| Prompt injection | T3-1 (input_sanitizer.py) | T5-3 |
| LLM output validation | T2-8 (output_validator.py) | T5-3 |
| Rate limiting (AI) | T3-1 (slowapi, 10/min) | T5-5 |
| Rate limiting (standard) | T3-1 (slowapi, 60/min) | T5-5 |
| Audit logging | T1-7 (audit trigger) | T3-4 tests |
| Mock gov enforcement | T3-4 (complaint_service) | T3-4 tests |
| Secrets management | T0-3 + T0-5 (env vars) | Manual review |

### IDOR Test Matrix (T5-1)
```
Citizen A creates report_1, complaint_1, rti_1
Citizen B creates report_2, complaint_2, rti_2

Tests (all must return 403 or 404):
- Citizen B: GET /reports/report_1
- Citizen B: GET /complaints/complaint_1
- Citizen B: POST /complaints/complaint_1/submit
- Citizen B: GET /rti/rti_1
- Citizen B: POST /rti/rti_1/approve
- Citizen A: GET /admin/complaints (403)
- Authority officer: GET /complaints/complaint_1 (if different authority)
```

---

## Task-Level Test Matrix

| Task | Unit | Integration | API | DB/RLS | Security | AI | LLM | Frontend | E2E | RAM | Smoke |
|------|------|-------------|-----|--------|----------|----|-----|----------|-----|-----|-------|
| T0-2 | — | — | — | — | — | — | — | build ✓ | — | — | — |
| T0-3 | health ✓ | — | health ✓ | — | — | — | — | — | — | — | — |
| T0-4 | — | — | — | ext ✓ | — | — | — | — | — | — | — |
| T1-1 | — | — | — | enum ✓ | — | — | — | — | — | — | — |
| T1-2 | — | — | — | FK ✓ | — | — | — | — | — | — | — |
| T1-3 | — | — | — | idx ✓ | — | — | — | — | — | — | — |
| T1-4 | — | — | — | RLS ✓ | IDOR ✓ | — | — | — | — | — | — |
| T1-5 | — | seed ✓ | — | RLS ✓ | no-write ✓ | — | — | — | — | — | — |
| T1-6 | — | — | — | stor ✓ | RLS ✓ | — | — | — | — | — | — |
| T1-7 | — | trig ✓ | — | — | audit ✓ | — | — | — | — | — | — |
| T1-8 | login ✓ | profile ✓ | — | — | JWT ✓ | — | — | — | — | — | — |
| T2-1 | ram ✓ | dep ✓ | — | — | — | — | — | — | — | ram ✓ | — |
| T2-2 | valid ✓ | — | — | — | MIME ✓ | — | — | — | — | — | — |
| T2-3 | blur ✓ | — | — | — | priv ✓ | face ✓ | — | — | — | — | — |
| T2-4 | redact ✓ | — | — | — | priv ✓ | plate ✓ | — | — | — | — | — |
| T2-5 | yolo ✓ | — | — | — | — | det ✓ | — | — | — | ram ✓ | — |
| T2-6 | score ✓ | — | — | — | — | conf ✓ | — | — | — | — | — |
| T2-7 | hash ✓ | dup ✓ | — | — | — | — | — | — | — | — | — |
| T2-8 | schema ✓ | — | — | — | inject ✓ | — | groq ✓ | — | — | — | — |
| T2-9 | tmpl ✓ | — | — | — | — | — | fallb ✓ | — | — | — | — |
| T2-10 | orch ✓ | — | — | — | — | — | both ✓ | — | — | — | — |
| T2-11 | e2e ✓ | pipeline ✓ | — | — | — | full ✓ | — | — | — | ram ✓ | — |
| T2-12 | embed ✓ | vec ✓ | — | — | — | — | — | — | — | gate ✓ | — |
| T2-13 | chunk ✓ | seed ✓ | — | — | — | — | — | — | — | — | — |
| T3-1 | auth ✓ | — | JWT ✓ | — | RBAC ✓ | — | — | — | — | — | — |
| T3-2 | route ✓ | — | — | — | — | — | — | — | — | — | — |
| T3-3 | upload ✓ | rpt ✓ | POST ✓ | — | MIME ✓ | — | — | — | — | — | smk ✓ |
| T3-4 | SM ✓ | cmplt ✓ | CRUD ✓ | — | IDOR ✓ | — | — | — | — | — | smk ✓ |
| T3-5 | elig ✓ | rti ✓ | RTI ✓ | — | IDOR ✓ | — | — | — | — | — | smk ✓ |
| T3-6 | admin ✓ | — | adm ✓ | — | RBAC ✓ | — | — | — | — | — | — |
| T3-7 | pub ✓ | RT ✓ | — | — | — | — | — | — | — | — | — |
| T4-1 | types ✓ | — | client ✓ | — | JWT ✓ | — | — | — | — | — | — |
| T4-2 | form ✓ | — | — | — | — | — | — | RTL ✓ | — | — | — |
| T4-3 | — | — | — | — | — | — | — | RTL ✓ | — | — | — |
| T4-4 | cam ✓ | — | — | — | — | — | — | RTL ✓ | — | — | — |
| T4-5 | gps ✓ | map ✓ | — | — | — | — | — | RTL ✓ | — | — | — |
| T4-6 | flow ✓ | offline ✓ | — | — | — | — | — | RTL ✓ | E2E ✓ | — | — |
| T4-7 | edit ✓ | submit ✓ | — | — | — | — | — | RTL ✓ | E2E ✓ | — | — |
| T4-8 | RT ✓ | — | — | — | — | — | — | RTL ✓ | E2E ✓ | — | — |
| T4-9 | rti ✓ | — | — | — | — | — | — | RTL ✓ | E2E ✓ | — | — |
| T4-10 | role ✓ | — | — | — | RBAC ✓ | — | — | RTL ✓ | E2E ✓ | — | — |
| T4-11 | sw ✓ | — | — | — | — | — | — | — | LH ✓ | — | — |
| T4-12 | idb ✓ | retry ✓ | — | — | — | — | — | Jest ✓ | E2E ✓ | — | — |
| T5-1 | — | — | — | RLS ✓ | IDOR ✓ | — | — | — | — | — | — |
| T5-2 | — | — | — | — | upl ✓ | — | — | — | — | — | — |
| T5-3 | — | — | — | — | inj ✓ | — | llm ✓ | — | — | — | — |
| T5-4 | — | — | — | — | — | — | — | — | E2E ✓ | — | — |
| T5-5 | — | — | rl ✓ | — | rate ✓ | — | — | — | — | — | — |
| T5-6 | — | cons ✓ | — | cons ✓ | cons ✓ | — | — | — | — | — | — |
| T6-5 | — | — | — | — | — | — | — | — | PW ✓ | — | smk ✓ |
| T6-6 | — | — | — | — | — | — | — | — | — | — | demo ✓ |

*Legend: SM=state machine, RT=realtime, sw=service worker, LH=Lighthouse, PW=Playwright, idb=IndexedDB, conf=confidence, det=detection, tmpl=template, orch=orchestrator, cons=consistency, rl=rate-limit, inj=injection, llm=LLM schema, priv=privacy, val=validation, dup=duplicate, ext=extensions, idx=indexes, trig=trigger, stor=storage, dep=dependencies, rpt=report, cmplt=complaint, elig=eligibility, adm=admin, pub=publish, cam=camera, gps=GPS*


---

## AGENT EXECUTION ORDER

> This section defines the exact prompt objectives, allowed scope, file
> constraints, and completion definitions for each implementation agent
> that will be given a task from this plan.
>
> No implementation agent may redesign architecture, change technology
> choices, or make decisions not already resolved in Part A.
> All agents must read this plan before starting their task.

---

### Agent Task: T0-1 — Repository Scaffolding

- **Task ID:** T0-1
- **Prompt objective:** Create the monorepo directory structure, root .gitignore, and root README.md exactly as specified in Part A §36 of the canonical plan document.
- **Allowed scope:** Create directories; create README.md; create .gitignore
- **Files allowed to modify:** `README.md`, `.gitignore`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, any existing source files
- **Dependencies that must already be complete:** None
- **Required tests:** Manual verification: all directories from Part A §36 exist
- **Definition of completion:** Repository structure matches Part A §36; .gitignore covers node_modules, __pycache__, .env*, *.pyc
- **Required handoff message:** "T0-1 complete. Repo structure confirmed. Directory list: [list directories]. Branch strategy: main + feature branches."

---

### Agent Task: T0-2 — Frontend Project Bootstrap

- **Task ID:** T0-2
- **Prompt objective:** Initialize Next.js 14 App Router project with TypeScript 5.x, Tailwind CSS 3.x, and shadcn/ui. Create .env.local.example with all required frontend env vars.
- **Allowed scope:** `frontend/` directory only
- **Files allowed to modify:** All files within `frontend/`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T0-1
- **Required tests:** `npm run build` must pass with zero TypeScript errors
- **Definition of completion:** `npm run dev` starts; `npm run build` passes; Tailwind renders; shadcn/ui initialized
- **Required handoff message:** "T0-2 complete. Next.js 14 App Router running. TypeScript build passes. Tailwind + shadcn/ui configured. localhost:3000 confirmed."

---

### Agent Task: T0-3 — Backend Project Bootstrap

- **Task ID:** T0-3
- **Prompt objective:** Initialize FastAPI 0.111.x project with Python 3.11. Create requirements.txt, main.py, config.py, health router, and .env.example. No business logic.
- **Allowed scope:** `backend/` directory only
- **Files allowed to modify:** All files within `backend/`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T0-1
- **Required tests:** `pytest` passes; `GET /health` → 200
- **Definition of completion:** `uvicorn main:app --reload` starts without errors; `/health` returns 200; Pydantic Settings loads from .env
- **Required handoff message:** "T0-3 complete. FastAPI running on localhost:8000. /health → 200 confirmed. requirements.txt finalized."

---

### Agent Task: T0-4 — Supabase Project Initialization

- **Task ID:** T0-4
- **Prompt objective:** Create Supabase project in ap-south-1 region. Enable postgis, pgvector, uuid-ossp extensions. Verify extensions active. Distribute credentials securely.
- **Allowed scope:** Supabase dashboard configuration only; no code files
- **Files allowed to modify:** None (Supabase dashboard only)
- **Files that must NOT be modified:** All source files
- **Dependencies that must already be complete:** T0-1
- **Required tests:** `SELECT postgis_version()` returns result; `SELECT * FROM pg_extension WHERE extname='vector'` returns result
- **Definition of completion:** Supabase project live in ap-south-1; all 3 extensions enabled; credentials distributed to M1, M2, M4
- **Required handoff message:** "T0-4 complete. Supabase URL: [url]. Extensions enabled: postgis, pgvector, uuid-ossp. Credentials distributed."

---

### Agent Task: T0-5 — CI/CD Pipeline Setup

- **Task ID:** T0-5
- **Prompt objective:** Create GitHub Actions CI workflow (PR: lint+typecheck+pytest) and deploy workflow (push to main: Vercel+Render hooks). Configure GitHub secrets.
- **Allowed scope:** `.github/workflows/` directory only
- **Files allowed to modify:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all source files
- **Dependencies that must already be complete:** T0-2, T0-3
- **Required tests:** CI workflow runs on PR and passes; green badge on README
- **Definition of completion:** PR triggers CI; lint + typecheck + pytest all pass; green CI badge visible
- **Required handoff message:** "T0-5 complete. CI green on main. GitHub Actions configured. Secrets: VERCEL_TOKEN, RENDER_DEPLOY_HOOK_URL added."

---

### Agent Task: T1-1 — Database Enums

- **Task ID:** T1-1
- **Prompt objective:** Create `supabase/migrations/001_enums.sql` with all four PostgreSQL enums as specified in Part A §7 and the Database Implementation Plan in Part B.
- **Allowed scope:** `supabase/migrations/001_enums.sql`
- **Files allowed to modify:** `supabase/migrations/001_enums.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T0-4
- **Required tests:** SQL verification: `SELECT enum_range(NULL::complaint_status)` returns 6 values; all 4 enums exist
- **Definition of completion:** All 4 enums created with exact values from Part A §7
- **Required handoff message:** "T1-1 complete. Enums: complaint_status(6), rti_status(6), issue_category(10), user_role(3). Migration 001_enums.sql applied."

---

### Agent Task: T1-2 — Core Table Creation

- **Task ID:** T1-2
- **Prompt objective:** Create `supabase/migrations/002_tables.sql` with all 7 tables as specified in Part A §21 and the Database Implementation Plan in Part B. Include all columns, types, FKs, and the audit_log append-only constraint.
- **Allowed scope:** `supabase/migrations/002_tables.sql`
- **Files allowed to modify:** `supabase/migrations/002_tables.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T1-1
- **Required tests:** Insert test row into each table; FK violation test; vector column exists on rti_knowledge_base; geography column exists on reports
- **Definition of completion:** All 7 tables exist with correct schema; all FK constraints enforced
- **Required handoff message:** "T1-2 complete. Tables: profiles, authorities, reports, complaints, rti_requests, rti_knowledge_base, audit_log. All FK constraints verified. Migration 002_tables.sql applied."

---

### Agent Task: T1-3 — Database Indexes

- **Task ID:** T1-3
- **Prompt objective:** Create `supabase/migrations/003_indexes.sql` with all performance indexes as specified in Part B Database Implementation Plan.
- **Allowed scope:** `supabase/migrations/003_indexes.sql`
- **Files allowed to modify:** `supabase/migrations/003_indexes.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T1-2
- **Required tests:** EXPLAIN ANALYZE on location query confirms GiST index used; all indexes visible in \di
- **Definition of completion:** All 6 indexes created including GiST on location and IVFFlat on embedding
- **Required handoff message:** "T1-3 complete. Indexes: GiST(location), IVFFlat(embedding), composite(user_id,status), authority_id, audit_log(user_id, entity_id). Migration 003_indexes.sql applied."

---

### Agent Task: T1-4 — Row Level Security Policies

- **Task ID:** T1-4
- **Prompt objective:** Create `supabase/migrations/004_rls.sql`. Enable RLS on all 7 tables. Implement all access policies as specified in Part B Database Implementation Plan. Test IDOR: citizen A cannot see citizen B's data.
- **Allowed scope:** `supabase/migrations/004_rls.sql`
- **Files allowed to modify:** `supabase/migrations/004_rls.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T1-2
- **Required tests:** RLS test suite: citizen A cannot SELECT citizen B's complaints; admin can SELECT all; service role can INSERT audit_log; anon cannot
- **Definition of completion:** RLS enabled on all 7 tables; all policies implemented; IDOR cross-user test passes
- **Required handoff message:** "T1-4 complete. RLS enabled: profiles, reports, complaints, rti_requests, rti_knowledge_base, audit_log. IDOR test: PASS. Admin full-access test: PASS."

---

### Agent Task: T1-5 — Authority Seed Data

- **Task ID:** T1-5
- **Prompt objective:** Create `backend/data/mangaluru_authorities.json` with Mangaluru authority records. Create `supabase/seed/001_authorities.sql` to seed the authorities table. Verify no application-level writes are possible.
- **Allowed scope:** `backend/data/mangaluru_authorities.json`, `supabase/seed/001_authorities.sql`
- **Files allowed to modify:** `backend/data/mangaluru_authorities.json`, `supabase/seed/001_authorities.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `supabase/migrations/`
- **Dependencies that must already be complete:** T1-4
- **Required tests:** Seed row count > 0; all 10 issue_category values covered by at least one authority; INSERT via citizen JWT fails
- **Definition of completion:** authorities.json created; seed SQL applied; all categories have a default authority; RLS prevents citizen INSERT
- **Required handoff message:** "T1-5 complete. authorities.json: [N] authorities. All 10 categories covered. Seed SQL applied. Write protection: PASS."

---

### Agent Task: T1-6 — Storage Buckets and Storage RLS

- **Task ID:** T1-6
- **Prompt objective:** Create all four Supabase Storage buckets (report-originals, report-redacted, resolution-photos, rti-documents) with `public=false` and configure RLS policies per Part A §20 and Part B Storage section.
- **Allowed scope:** Supabase Storage configuration (dashboard or SQL)
- **Files allowed to modify:** `supabase/migrations/` (if using SQL to configure storage)
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T1-4
- **Required tests:** Storage RLS test: citizen A download of citizen B's report-original → denied; admin download → allowed; all 4 buckets exist with public=false
- **Definition of completion:** 4 buckets created; none public; Storage RLS mirrors DB RLS
- **Required handoff message:** "T1-6 complete. Buckets: report-originals, report-redacted, resolution-photos, rti-documents. All private. Storage RLS: PASS."

---

### Agent Task: T1-7 — Audit Log Trigger

- **Task ID:** T1-7
- **Prompt objective:** Create `supabase/migrations/005_audit_trigger.sql` with PostgreSQL triggers on complaints and rti_requests status changes that insert into audit_log.
- **Allowed scope:** `supabase/migrations/005_audit_trigger.sql`
- **Files allowed to modify:** `supabase/migrations/005_audit_trigger.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T1-2, T1-4
- **Required tests:** UPDATE complaints.status → audit_log row auto-created; trigger fires with correct entity_type and old/new status
- **Definition of completion:** Triggers on complaints + rti_requests; audit_log populated automatically on status change
- **Required handoff message:** "T1-7 complete. Audit triggers: complaints_audit, rti_audit. Test: status change → audit_log INSERT confirmed."

---

### Agent Task: T1-8 — Auth Configuration and Profile Trigger

- **Task ID:** T1-8
- **Prompt objective:** Enable Supabase email/password auth. Create `supabase/migrations/006_auth_trigger.sql` for profile auto-creation. Create demo user accounts. Confirm JWT structure.
- **Allowed scope:** `supabase/migrations/006_auth_trigger.sql`; Supabase Auth dashboard configuration
- **Files allowed to modify:** `supabase/migrations/006_auth_trigger.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T1-2, T1-4
- **Required tests:** Register user → profile row auto-created with role=citizen; login → JWT returned; JWT sub = user_id
- **Definition of completion:** Email/password auth working; profile auto-created on registration; demo users created; JWT verified
- **Required handoff message:** "T1-8 complete. Auth enabled. Profile trigger: PASS. Demo users: citizen_demo@civicai.test, admin_demo@civicai.test. JWT structure confirmed. Credentials distributed."

---

### Agent Task: T2-1 — AI Dependency Installation and RAM Validation

- **Task ID:** T2-1
- **Prompt objective:** Add all AI/CV dependencies to `backend/requirements.txt`. Create `backend/cv/ram_check.py` with RAM gate logic per Part A §8 and Part B AI/CV Implementation Plan.
- **Allowed scope:** `backend/requirements.txt`, `backend/cv/ram_check.py`
- **Files allowed to modify:** `backend/requirements.txt`, `backend/cv/ram_check.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T0-3
- **Required tests:** `pip install -r requirements.txt` succeeds; ram_check.py test passes
- **Definition of completion:** All AI deps in requirements.txt; RAM check utility functional; no models loaded at startup
- **Required handoff message:** "T2-1 complete. AI deps added: ultralytics, opencv-python-headless, fast-alpr, sentence-transformers, groq, psutil. RAM check utility: PASS."

---

### Agent Task: T2-2 — Image Validation

- **Task ID:** T2-2
- **Prompt objective:** Create `backend/cv/image_validator.py` with MIME type check, magic bytes check, file size check, minimum dimensions check, Pillow re-encode, and resize-to-1024px. Per Part A §13, §28 and Part B AI/CV Implementation Plan.
- **Allowed scope:** `backend/cv/image_validator.py`
- **Files allowed to modify:** `backend/cv/image_validator.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-1
- **Required tests:** pytest — malformed MIME → exception; oversized → exception; non-image → exception; valid JPEG → accepted and re-encoded; EXIF stripped
- **Definition of completion:** All 4+ validation tests pass; Pillow re-encode strips EXIF; resize works
- **Required handoff message:** "T2-2 complete. image_validator.py: MIME ✓, magic bytes ✓, size ✓, dimensions ✓, re-encode ✓, resize ✓. Tests: PASS."

---

### Agent Task: T2-3 — Face Redaction

- **Task ID:** T2-3
- **Prompt objective:** Create `backend/cv/privacy.py` with `redact_faces(image)` function using YuNet ONNX with lazy loading. Apply Gaussian blur to all detected face bounding boxes. Per Part A §8, §14.
- **Allowed scope:** `backend/cv/privacy.py`
- **Files allowed to modify:** `backend/cv/privacy.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-2
- **Required tests:** Test image with face → blur applied to face region; test image without face → unchanged; model not loaded at import time
- **Definition of completion:** `redact_faces` function works; lazy loading confirmed; face in test image is blurred
- **Required handoff message:** "T2-3 complete. redact_faces: face blurred ✓, no-face unchanged ✓, lazy load ✓."

---

### Agent Task: T2-4 — Plate Redaction

- **Task ID:** T2-4
- **Prompt objective:** Extend `backend/cv/privacy.py` with `redact_plates(image)` using fast-alpr with lazy loading. Apply black rectangle to detected plate bounding boxes. Per Part A §8, §14.
- **Allowed scope:** `backend/cv/privacy.py`
- **Files allowed to modify:** `backend/cv/privacy.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-3
- **Required tests:** Test image with plate → black rectangle over plate; test image without plate → unchanged; model not loaded at import time
- **Definition of completion:** `redact_plates` function works; lazy loading confirmed; plate in test image is redacted
- **Required handoff message:** "T2-4 complete. redact_plates: plate redacted ✓, no-plate unchanged ✓, lazy load ✓."

---

### Agent Task: T2-5 — YOLO Detection and Taxonomy Mapping

- **Task ID:** T2-5
- **Prompt objective:** Create `backend/cv/detection.py` with YOLOv8n lazy-load inference. Create `backend/cv/taxonomy.py` with YOLO class → issue_category mapping. Per Part A §8 and Part B AI/CV Implementation Plan.
- **Allowed scope:** `backend/cv/detection.py`, `backend/cv/taxonomy.py`
- **Files allowed to modify:** `backend/cv/detection.py`, `backend/cv/taxonomy.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-2
- **Required tests:** Known civic image → correct category returned with confidence > 0; unknown class → `other` returned; lazy load confirmed
- **Definition of completion:** YOLO detection works; taxonomy covers all 10 issue categories; `other` is the default for unmapped classes
- **Required handoff message:** "T2-5 complete. detection.py + taxonomy.py. YOLO inference: ✓. Taxonomy: all 10 categories mapped. Lazy load: ✓."

---

### Agent Task: T2-6 — Evidence Confidence Scoring

- **Task ID:** T2-6
- **Prompt objective:** Create `backend/cv/confidence.py` with `compute_confidence(detection_confidence, category)` returning a score in 0.0–1.0. Per Part A §8 and Part B AI/CV Implementation Plan.
- **Allowed scope:** `backend/cv/confidence.py`
- **Files allowed to modify:** `backend/cv/confidence.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-5
- **Required tests:** High confidence pothole → score > 0.7; low confidence other → score < 0.5; output always 0.0–1.0
- **Definition of completion:** `compute_confidence` returns correct scores; all boundary cases handled
- **Required handoff message:** "T2-6 complete. confidence.py. Score formula: detection_confidence × category_weight. Range: 0.0–1.0. Tests: PASS."

---

### Agent Task: T2-7 — Image Hash and Duplicate Detection

- **Task ID:** T2-7
- **Prompt objective:** Add blake3 image hashing to the pipeline. Implement duplicate detection using PostGIS ST_DWithin (50m radius) + hash match query against reports table. Per Part A §11 and Part B AI/CV Implementation Plan.
- **Allowed scope:** `backend/cv/pipeline.py` (hash function), duplicate query in `backend/db/repositories/report_repo.py`
- **Files allowed to modify:** `backend/cv/pipeline.py`, `backend/db/repositories/report_repo.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T2-2, T1-2
- **Required tests:** Same image bytes → same hash; duplicate detected for nearby same-category report; not blocked (advisory only)
- **Definition of completion:** blake3 hash computed; duplicate check query works; is_duplicate flag returned (not a blocker)
- **Required handoff message:** "T2-7 complete. blake3 hash: ✓. Duplicate detection (ST_DWithin 50m + hash): ✓. Duplicate flag is advisory (non-blocking)."

---

### Agent Task: T2-8 — LLM Groq Integration

- **Task ID:** T2-8
- **Prompt objective:** Create `backend/llm/prompts.py`, `backend/llm/groq_provider.py`, and `backend/llm/output_validator.py`. Implement async Groq API calls with structured output, Pydantic schema validation, and prompt injection protection. Per Part A §9 and Part B AI/CV Implementation Plan.
- **Allowed scope:** `backend/llm/prompts.py`, `backend/llm/groq_provider.py`, `backend/llm/output_validator.py`
- **Files allowed to modify:** `backend/llm/prompts.py`, `backend/llm/groq_provider.py`, `backend/llm/output_validator.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-1
- **Required tests:** Valid Groq response → LLMOutput populated; invalid JSON → exception; schema violation → exception; prompt injection string → sanitized
- **Definition of completion:** Groq provider works; output validated; injection strings neutralized
- **Required handoff message:** "T2-8 complete. groq_provider.py + output_validator.py. Schema validation: ✓. Injection protection: ✓. Model: llama-3.1-8b-instant confirmed."

---

### Agent Task: T2-9 — LLM Fallback + Watsonx Stub

- **Task ID:** T2-9
- **Prompt objective:** Create `backend/llm/fallback_provider.py` with deterministic templates for all 3 use cases. Create `backend/llm/watsonx_stub.py` as a NOT-wired stub. Per Part A §9.
- **Allowed scope:** `backend/llm/fallback_provider.py`, `backend/llm/watsonx_stub.py`
- **Files allowed to modify:** `backend/llm/fallback_provider.py`, `backend/llm/watsonx_stub.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-8
- **Required tests:** Fallback returns valid LLMOutput for all 3 use cases; Groq mock failure → fallback used; watsonx_stub.raise NotImplementedError
- **Definition of completion:** Fallback works for complaint description, RTI draft, category classification; Watsonx stub NOT wired
- **Required handoff message:** "T2-9 complete. fallback_provider.py: all 3 templates. watsonx_stub.py: NotImplementedError stub. Fallback trigger on Groq failure: ✓."

---

### Agent Task: T2-10 — LLM Service Orchestrator

- **Task ID:** T2-10
- **Prompt objective:** Create `backend/services/llm_service.py` that tries Groq first and falls back to deterministic template on failure. Expose three public methods: generate_complaint_description, generate_rti_draft, classify_category. Per Part A §9.
- **Allowed scope:** `backend/services/llm_service.py`
- **Files allowed to modify:** `backend/services/llm_service.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-8, T2-9
- **Required tests:** Groq available → Groq used; Groq unavailable → fallback used; both paths return same LLMOutput schema
- **Definition of completion:** Provider chain Groq→fallback works transparently; all 3 methods implemented
- **Required handoff message:** "T2-10 complete. llm_service.py. Provider chain: Groq → deterministic fallback. All 3 methods: ✓. Schema consistency: ✓."

---

### Agent Task: T2-11 — AI Pipeline Orchestrator

- **Task ID:** T2-11
- **Prompt objective:** Create `backend/cv/pipeline.py` with `run_ai_pipeline(image_bytes, location)` integrating all CV + LLM steps per the AI Flow in Part A §23. Return complete AIResult. Implement memory cleanup. Per Part A §8, §23, §29.
- **Allowed scope:** `backend/cv/pipeline.py`
- **Files allowed to modify:** `backend/cv/pipeline.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T2-3, T2-4, T2-5, T2-6, T2-7, T2-10
- **Required tests:** End-to-end with test civic image → complete AIResult returned; memory < 400 MB after pipeline; partial failure (YOLO fails) → graceful fallback to category=other
- **Definition of completion:** Full pipeline functional; AIResult schema complete; memory within budget; partial failures handled
- **Required handoff message:** "T2-11 complete. run_ai_pipeline: ✓. AIResult fields: all present. Memory after run: [X] MB (< 400 MB). Partial failure: category=other fallback ✓."

---

### Agent Task: T2-12 — RAG Infrastructure

- **Task ID:** T2-12
- **Prompt objective:** Create `backend/rag/embedder.py` (BAAI embedding with RAM gate), `backend/rag/vector_store.py` (pgvector cosine search), and `backend/rag/retriever.py` (vector or keyword fallback). Per Part A §10 and Part B RAG Implementation Plan.
- **Allowed scope:** `backend/rag/embedder.py`, `backend/rag/vector_store.py`, `backend/rag/retriever.py`
- **Files allowed to modify:** `backend/rag/embedder.py`, `backend/rag/vector_store.py`, `backend/rag/retriever.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T2-1, T1-3
- **Required tests:** Vector search returns top-5 chunks; keyword fallback works when embedding disabled; RAM gate correctly sets EMBEDDING_ENABLED=False
- **Definition of completion:** Retriever returns relevant chunks via vector or keyword; RAM gate works
- **Required handoff message:** "T2-12 complete. embedder.py: BAAI lazy + RAM gate ✓. vector_store.py: cosine search ✓. retriever.py: vector + keyword fallback ✓."

---

### Agent Task: T2-13 — RTI Knowledge Base Ingestion

- **Task ID:** T2-13
- **Prompt objective:** Create `backend/rag/chunker.py` for 512-token chunking. Create RTI knowledge base content (RTI Act sections, MCC procedures). Ingest and store in rti_knowledge_base table. Per Part A §10 and Part B RAG Implementation Plan.
- **Allowed scope:** `backend/rag/chunker.py`, `supabase/seed/002_rti_knowledge_base.sql` or Python ingestion script
- **Files allowed to modify:** `backend/rag/chunker.py`, `supabase/seed/002_rti_knowledge_base.sql`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T2-12, T1-2
- **Required tests:** `SELECT COUNT(*) FROM rti_knowledge_base` > 0; retrieval returns relevant chunks for a test RTI query
- **Definition of completion:** Knowledge base seeded with RTI Act + MCC content; retrieval tested
- **Required handoff message:** "T2-13 complete. RTI knowledge base: [N] chunks. Retrieval test: relevant chunks returned for 'complaint no response 30 days' query."

---

### Agent Task: T3-1 — Backend Core Infrastructure

- **Task ID:** T3-1
- **Prompt objective:** Create `backend/security/jwt_verify.py`, `rbac.py`, `ownership.py`, `input_sanitizer.py`, and `backend/dependencies.py`. Configure slowapi rate limits (10/min AI, 60/min standard). Configure CORS. Per Part A §13, §19 and Part B Backend Implementation Plan.
- **Allowed scope:** `backend/security/`, `backend/dependencies.py`, `backend/main.py` (middleware only)
- **Files allowed to modify:** `backend/security/jwt_verify.py`, `backend/security/rbac.py`, `backend/security/ownership.py`, `backend/security/input_sanitizer.py`, `backend/dependencies.py`, `backend/main.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T0-3, T1-8
- **Required tests:** Valid JWT → user extracted; invalid JWT → 401; expired JWT → 401; wrong role → 403; rate limit exceeded → 429; CORS from wrong origin → rejected
- **Definition of completion:** All security middleware active; JWT verification works with real Supabase JWT
- **Required handoff message:** "T3-1 complete. jwt_verify: RS256 ✓. RBAC: 3 roles ✓. IDOR ownership: ✓. Rate limits: 10/min AI, 60/min standard ✓. CORS: restricted ✓."

---

### Agent Task: T3-2 — Authority Routing Service

- **Task ID:** T3-2
- **Prompt objective:** Create `backend/services/authority_service.py` and `backend/db/repositories/authority_repo.py`. Load mangaluru_authorities.json at startup. Implement routing by `category` (issue_type) and `address_text` (area keyword match) ONLY — per Part A §12 and ADR-001. Do NOT use ward_range, ward numbers, GeoJSON, or PostGIS for routing. See the T3-2 task definition in Part B for exact function signature and step-by-step routing logic.
- **Allowed scope:** `backend/services/authority_service.py`, `backend/db/repositories/authority_repo.py`
- **Files allowed to modify:** `backend/services/authority_service.py`, `backend/db/repositories/authority_repo.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/data/mangaluru_authorities.json`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T1-5, T3-1
- **Required tests:** All 10 categories return a valid authority; address_text keyword match works; no-match → first category default returned; no PostGIS calls in routing path; JSON loaded at startup (not from DB)
- **Definition of completion:** Authority routing works for all 10 categories using category + area_text keyword only; JSON is sole source of truth; DB never queried; no ward_range or PostGIS used
- **Required handoff message:** "T3-2 complete. authority_service.py. Routing: category + area_text keyword ✓. All 10 categories ✓. No PostGIS in routing ✓. JSON-only (no DB queries) ✓."

---

### Agent Task: T3-3 — Report Service and Router

- **Task ID:** T3-3
- **Prompt objective:** Create `backend/db/repositories/report_repo.py`, `backend/services/report_service.py`, and `backend/routers/reports.py`. Implement POST /reports/ (multipart image + location → AI pipeline → DB + storage) and GET /reports/{id} (with signed URLs). Per Part A §6, §18, §22 and Part B Backend Implementation Plan.
- **Allowed scope:** `backend/db/repositories/report_repo.py`, `backend/services/report_service.py`, `backend/routers/reports.py`, `backend/services/storage_service.py`
- **Files allowed to modify:** All files listed in Allowed scope
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T2-11, T3-1, T3-2, T1-6
- **Required tests:** Valid image upload → report created; AI results in response; invalid MIME → 422; no JWT → 401; GET returns signed URLs (15-min expiry)
- **Definition of completion:** Full report creation flow working; no business logic in route handler; signed URLs generated
- **Required handoff message:** "T3-3 complete. POST /reports/: upload → AI → DB → signed URLs ✓. GET /reports/{id}: signed URLs ✓. Service layer: all logic in report_service.py ✓."

---

### Agent Task: T3-4 — Complaint Service and Router

- **Task ID:** T3-4
- **Prompt objective:** Create `backend/db/repositories/complaint_repo.py`, `backend/services/complaint_service.py`, and `backend/routers/complaints.py`. Implement full complaint CRUD, submit (DRAFT→SUBMITTED), mock gov ref, admin status updates, and resolution. Enforce all state machine transitions from Part A §24.
- **Allowed scope:** `backend/db/repositories/complaint_repo.py`, `backend/services/complaint_service.py`, `backend/routers/complaints.py`
- **Files allowed to modify:** All files listed in Allowed scope
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T3-1, T3-3
- **Required tests:** All valid state transitions; all invalid transitions → 409; mock_gov_ref generated; IDOR: citizen cannot submit other's complaint; audit log entry created on status change
- **Definition of completion:** All complaint API endpoints working; state machine enforced; mock gov ref generated; audit triggered
- **Required handoff message:** "T3-4 complete. Complaint API: CRUD ✓, submit ✓, mock_gov_ref ✓, admin update ✓, resolve ✓. State machine: all transitions enforced ✓. IDOR: ✓. Audit trigger: ✓."

---

### Agent Task: T3-5 — RTI Service and Router

- **Task ID:** T3-5
- **Prompt objective:** Create `backend/db/repositories/rti_repo.py`, `backend/services/rti_service.py`, and `backend/routers/rti.py`. Implement RTI eligibility check (30-day rule), draft creation (RAG + LLM), approval, and mock submission. Enforce RTI state machine from Part A §25.
- **Allowed scope:** `backend/db/repositories/rti_repo.py`, `backend/services/rti_service.py`, `backend/routers/rti.py`
- **Files allowed to modify:** All files listed in Allowed scope
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T3-1, T3-4, T2-10, T2-12
- **Required tests:** Eligible complaint → RTI draft created with LLM text; resolved complaint → 422; complaint < 30 days → 422; duplicate RTI → 422; approve → rti_ref generated; IDOR test
- **Definition of completion:** RTI eligibility enforced; draft uses RAG+LLM (or fallback); mock rti_ref generated; state machine enforced
- **Required handoff message:** "T3-5 complete. RTI API: eligibility ✓, draft (RAG+LLM) ✓, approve ✓, mock rti_ref ✓. State machine: ✓. IDOR: ✓."

---

### Agent Task: T3-6 — Admin Router

- **Task ID:** T3-6
- **Prompt objective:** Create `backend/routers/admin.py` with GET /admin/complaints (paginated), PATCH /complaints/{id}/status, and POST /complaints/{id}/resolve. All routes require admin role.
- **Allowed scope:** `backend/routers/admin.py`
- **Files allowed to modify:** `backend/routers/admin.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/`
- **Dependencies that must already be complete:** T3-1, T3-4
- **Required tests:** Admin JWT → all complaints listed; citizen JWT → 403; status update → audit log entry; resolve → resolution_image_path stored
- **Definition of completion:** All admin endpoints protected by RBAC; no business logic in router (uses complaint_service)
- **Required handoff message:** "T3-6 complete. Admin routes: GET /admin/complaints ✓, PATCH status ✓, POST resolve ✓. RBAC guard: ✓."

---

### Agent Task: T3-7 — Supabase Realtime Publishing

- **Task ID:** T3-7
- **Prompt objective:** Create `backend/services/realtime_service.py`. Publish to Supabase Realtime channel `complaints:{id}` on every complaint status change. Called from complaint_service.
- **Allowed scope:** `backend/services/realtime_service.py`
- **Files allowed to modify:** `backend/services/realtime_service.py`, `backend/services/complaint_service.py` (add publish calls)
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `frontend/`, `supabase/migrations/`
- **Dependencies that must already be complete:** T3-4
- **Required tests:** Complaint status change → Realtime event published with correct payload `{complaint_id, new_status, updated_at}`
- **Definition of completion:** Realtime events published on SUBMITTED, UNDER_REVIEW, RESOLVED, REJECTED transitions
- **Required handoff message:** "T3-7 complete. realtime_service.py. Publish on status change: ✓. Channel: complaints:{id}. Payload schema: {complaint_id, new_status, updated_at}."

---

### Agent Task: T4-1 — Frontend Supabase and API Client

- **Task ID:** T4-1
- **Prompt objective:** Create `frontend/lib/supabase.ts`, `frontend/lib/api-client.ts`, and `frontend/lib/types.ts`. API client must attach JWT Bearer header and parse `{data, error}` response envelope. Types must match all backend Pydantic schemas.
- **Allowed scope:** `frontend/lib/supabase.ts`, `frontend/lib/api-client.ts`, `frontend/lib/types.ts`
- **Files allowed to modify:** All files listed in Allowed scope
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T0-2, T1-8, T3-1
- **Required tests:** Jest — valid API response parsed; error envelope parsed; JWT attached; TypeScript build passes
- **Definition of completion:** API client + Supabase client working; types compile without errors; JWT attached to all requests
- **Required handoff message:** "T4-1 complete. supabase.ts ✓. api-client.ts: JWT Bearer ✓, envelope ✓. types.ts: all backend schemas typed ✓. TypeScript build: PASS."

---

### Agent Task: T4-2 — Authentication Pages

- **Task ID:** T4-2
- **Prompt objective:** Create login and register pages with Zod + react-hook-form validation. Create auth-context.tsx with React Context for session. Create middleware.ts for unauthenticated redirects. Per Part A §19.
- **Allowed scope:** `frontend/app/(auth)/`, `frontend/lib/auth-context.tsx`, `frontend/middleware.ts`
- **Files allowed to modify:** All files listed in Allowed scope
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-1
- **Required tests:** Jest + RTL — login form submit; invalid credentials error; protected route without session → redirect to /login
- **Definition of completion:** Login works with demo users; session context available; middleware redirects unauthenticated users
- **Required handoff message:** "T4-2 complete. Login: ✓. Register: ✓. Auth context: ✓. Middleware redirect: ✓. Demo user login tested."

---

### Agent Task: T4-3 — Dashboard

- **Task ID:** T4-3
- **Prompt objective:** Create `frontend/app/dashboard/page.tsx` showing citizen's complaint list (SWR) and pending DRAFT_OFFLINE items from IndexedDB.
- **Allowed scope:** `frontend/app/dashboard/page.tsx`
- **Files allowed to modify:** `frontend/app/dashboard/page.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-1, T4-2
- **Required tests:** Jest + RTL — list renders; empty state; pending drafts section visible
- **Definition of completion:** Dashboard shows complaints + pending drafts; loading skeleton; empty state
- **Required handoff message:** "T4-3 complete. Dashboard: complaint list ✓, empty state ✓, pending drafts section ✓."

---

### Agent Task: T4-4 — Camera Capture Component

- **Task ID:** T4-4
- **Prompt objective:** Create `frontend/components/camera/CameraCapture.tsx` using MediaDevices API (rear camera, facingMode environment). Live viewfinder, capture, preview, retake. Returns JPEG blob. NO gallery fallback. Per Part A §1, §38.
- **Allowed scope:** `frontend/components/camera/CameraCapture.tsx`
- **Files allowed to modify:** `frontend/components/camera/CameraCapture.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-2
- **Required tests:** Jest + RTL — mock getUserMedia; capture returns blob; retake resets; camera unavailable → error message (no file input fallback)
- **Definition of completion:** Camera opens; blob returned; retake works; NO gallery fallback implemented
- **Required handoff message:** "T4-4 complete. CameraCapture: live viewfinder ✓, capture ✓, retake ✓, blob callback ✓, camera error message ✓. Gallery fallback: NOT implemented (correct)."

---

### Agent Task: T4-5 — GPS and MapLibre Location Component

- **Task ID:** T4-5
- **Prompt objective:** Create `frontend/components/map/LocationPicker.tsx` with browser GPS acquisition and MapLibre manual pin fallback. Initialize at Mangaluru viewport. Use OpenFreeMap tiles. Per Part A §11.
- **Allowed scope:** `frontend/components/map/LocationPicker.tsx`
- **Files allowed to modify:** `frontend/components/map/LocationPicker.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-2
- **Required tests:** Jest + RTL — mock geolocation success → pin shown; geolocation fail → empty map; manual click → location returned; viewport at Mangaluru
- **Definition of completion:** GPS or manual pin returns {lat, lng}; Mangaluru viewport default; OpenFreeMap tiles
- **Required handoff message:** "T4-5 complete. LocationPicker: GPS ✓, GPS fail → manual pin ✓, OpenFreeMap tiles ✓, Mangaluru default viewport ✓."

---

### Agent Task: T4-6 — Report Creation Page

- **Task ID:** T4-6
- **Prompt objective:** Create `frontend/app/report/new/page.tsx` orchestrating CameraCapture + LocationPicker → POST /reports/ → AI spinner → redirect to review. If offline → save as DRAFT_OFFLINE with idb-keyval (no background sync). Per Part A §15, §17.
- **Allowed scope:** `frontend/app/report/new/page.tsx`, `frontend/lib/offline-store.ts` (initial stub)
- **Files allowed to modify:** `frontend/app/report/new/page.tsx`, `frontend/lib/offline-store.ts`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-4, T4-5, T3-3
- **Required tests:** Online: submit → API call → redirect to review; Offline: saved to IndexedDB → "Saved offline" message; NO background sync registered
- **Definition of completion:** Full report creation flow; offline DRAFT_OFFLINE saves to IndexedDB; no background sync
- **Required handoff message:** "T4-6 complete. Report creation: online ✓, offline DRAFT_OFFLINE ✓. Background sync: NOT registered (correct)."

---

### Agent Task: T4-7 — AI Review Page

- **Task ID:** T4-7
- **Prompt objective:** Create `frontend/app/report/[id]/page.tsx` (review phase) displaying AI results with editable fields (category, description, authority). Citizen approves → creates complaint + submits → shows mock_gov_ref. Per Part A §38 items 3,4.
- **Allowed scope:** `frontend/app/report/[id]/page.tsx`
- **Files allowed to modify:** `frontend/app/report/[id]/page.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-6, T3-4
- **Required tests:** Jest + RTL — AI results displayed; all 3 fields editable; submit → mock_gov_ref shown; Zod validation prevents empty submission
- **Definition of completion:** Review page working; citizen can edit all AI fields; approve creates + submits complaint; mock_gov_ref displayed
- **Required handoff message:** "T4-7 complete. AI review: display ✓, edit category ✓, edit description ✓, edit authority ✓, approve → mock_gov_ref ✓. Zod validation ✓."

---

### Agent Task: T4-8 — Complaint Detail and Status Timeline

- **Task ID:** T4-8
- **Prompt objective:** Extend `frontend/app/report/[id]/page.tsx` for post-submission view. Add status timeline (SUBMITTED→UNDER_REVIEW→RESOLVED/REJECTED), Supabase Realtime subscription, RTI eligibility button. Per Part A §15, §22, §24.
- **Allowed scope:** `frontend/app/report/[id]/page.tsx`
- **Files allowed to modify:** `frontend/app/report/[id]/page.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-7, T3-7
- **Required tests:** Jest + RTL — status timeline renders correct step; Realtime update → SWR revalidates; RTI button visible when eligible; RTI button hidden when resolved
- **Definition of completion:** Status timeline active; Realtime subscription works; RTI button appears/disappears correctly
- **Required handoff message:** "T4-8 complete. Status timeline ✓. Realtime subscription: complaints:{id} ✓. RTI button: eligible ✓, resolved-hidden ✓."

---

### Agent Task: T4-9 — RTI Flow

- **Task ID:** T4-9
- **Prompt objective:** Create `frontend/app/report/[id]/rti/page.tsx`. Load RTI draft (POST /rti/), show editable AI-generated letter, citizen approves (POST /rti/{id}/approve), show rti_ref. Per Part A §16.
- **Allowed scope:** `frontend/app/report/[id]/rti/page.tsx`
- **Files allowed to modify:** `frontend/app/report/[id]/rti/page.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-8, T3-5
- **Required tests:** Jest + RTL — RTI draft displayed; editable; approve → rti_ref shown; ineligible complaint → error
- **Definition of completion:** RTI flow complete; draft editable; approve shows rti_ref
- **Required handoff message:** "T4-9 complete. RTI flow: draft ✓, edit ✓, approve → rti_ref ✓, ineligibility error ✓."

---

### Agent Task: T4-10 — Admin Screens

- **Task ID:** T4-10
- **Prompt objective:** Create `frontend/app/admin/page.tsx` with admin-only access (middleware check), complaint list, status update, and resolve form. Redirect non-admins to dashboard. Per Part A §5, §19.
- **Allowed scope:** `frontend/app/admin/page.tsx`
- **Files allowed to modify:** `frontend/app/admin/page.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-2, T3-6
- **Required tests:** Jest + RTL — admin access ✓; citizen → redirect to dashboard ✓; status update works ✓
- **Definition of completion:** Admin screens accessible to admin only; status updates work
- **Required handoff message:** "T4-10 complete. Admin screens: list ✓, status update ✓, resolve ✓. Role guard: citizen redirected ✓."

---

### Agent Task: T4-11 — PWA Service Worker

- **Task ID:** T4-11
- **Prompt objective:** Configure next-pwa (serwist) in next.config.js. Create public/manifest.json. Cache app shell routes. Network-first for API calls. No background sync. Per Part A §17.
- **Allowed scope:** `frontend/next.config.js`, `frontend/public/manifest.json`
- **Files allowed to modify:** `frontend/next.config.js`, `frontend/public/manifest.json`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-6
- **Required tests:** Lighthouse PWA audit; app shell loads offline; background sync NOT registered
- **Definition of completion:** Service worker generated; app shell cached; PWA manifest valid; no background sync
- **Required handoff message:** "T4-11 complete. PWA: service worker ✓, manifest ✓, app shell cached ✓. Background sync: NOT registered ✓. Lighthouse PWA: PASS."

---

### Agent Task: T4-12 — IndexedDB Offline Draft Storage

- **Task ID:** T4-12
- **Prompt objective:** Create `frontend/lib/offline-store.ts` with saveDraft, listDrafts, deleteDraft using idb-keyval. Integrate manual retry in dashboard Pending Drafts. NO automatic background retry. Per Part A §17.
- **Allowed scope:** `frontend/lib/offline-store.ts`, `frontend/app/dashboard/page.tsx` (pending drafts section)
- **Files allowed to modify:** `frontend/lib/offline-store.ts`, `frontend/app/dashboard/page.tsx`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, `backend/`, `supabase/`
- **Dependencies that must already be complete:** T4-6
- **Required tests:** Jest — save/list/delete draft; manual retry submits and deletes; NO automatic retry registered
- **Definition of completion:** IndexedDB draft storage works; manual retry deletes draft after success; no auto-retry
- **Required handoff message:** "T4-12 complete. offline-store.ts: save/list/delete ✓. Manual retry: submit → delete ✓. Auto-retry: NOT implemented ✓."

---

### Agent Task: T5-1 — IDOR and RLS Security Tests

- **Task ID:** T5-1
- **Prompt objective:** Write and run a comprehensive pytest security test suite covering all IDOR violations and RLS policy bypasses as defined in Part B Security Implementation Plan and IDOR Test Matrix. Minimum 20 tests.
- **Allowed scope:** New test files in `backend/tests/security/`
- **Files allowed to modify:** `backend/tests/security/test_idor.py`, `backend/tests/security/test_rls.py`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** Phase 1, Phase 3 complete
- **Required tests:** 20+ IDOR/RLS tests; all must pass
- **Definition of completion:** Zero IDOR violations; zero RLS bypasses; all 20+ tests pass
- **Required handoff message:** "T5-1 complete. IDOR tests: [N] passed. RLS tests: [N] passed. Zero cross-user data leaks confirmed."

---

### Agent Task: T5-4 — Playwright E2E Tests

- **Task ID:** T5-4
- **Prompt objective:** Create all 5 Playwright E2E spec files in `frontend/e2e/`. Cover login, report submit (camera mocked), RTI submit, admin update, and offline draft. Minimum 20 total assertions. Per Part A §27.
- **Allowed scope:** `frontend/e2e/`
- **Files allowed to modify:** `frontend/e2e/login.spec.ts`, `frontend/e2e/report-submit.spec.ts`, `frontend/e2e/rti-submit.spec.ts`, `frontend/e2e/admin-update.spec.ts`, `frontend/e2e/offline-draft.spec.ts`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** Phase 4 complete
- **Required tests:** All 5 spec files pass in CI
- **Definition of completion:** All 5 E2E specs pass; mobile viewport test passes; CI green
- **Required handoff message:** "T5-4 complete. E2E specs: login ✓, report-submit ✓, rti-submit ✓, admin-update ✓, offline-draft ✓. Mobile viewport: ✓. Total assertions: [N]."

---

### Agent Task: T6-5 — Deployment Smoke Tests

- **Task ID:** T6-5
- **Prompt objective:** Run pytest smoke test suite against production Render URL and Playwright smoke spec against production Vercel URL. All tests must pass against live deployment.
- **Allowed scope:** New test files in `backend/tests/smoke/` and `frontend/e2e/smoke.spec.ts`
- **Files allowed to modify:** `backend/tests/smoke/test_production.py`, `frontend/e2e/smoke.spec.ts`
- **Files that must NOT be modified:** `docs/CIVICAI_MASTER_ARCHITECTURE.md`, all application source files
- **Dependencies that must already be complete:** T6-1, T6-2, T6-4
- **Required tests:** All 6 API smoke tests pass; Playwright smoke passes against production
- **Definition of completion:** Production endpoints all return expected responses; Playwright smoke green
- **Required handoff message:** "T6-5 complete. API smoke: /health ✓, login ✓, POST /reports/ ✓, POST /complaints/ ✓, GET /complaints/ ✓, POST /rti/ ✓. Playwright smoke: ✓. Ready for demo dry run."

---

> **END OF PART B — EXECUTION-READY IMPLEMENTATION PLAN**
>
> This plan is derived entirely from the LOCKED Master Architecture in Part A.
> No implementation agent may modify any decision in Part A.
> All agents must re-read this canonical document before beginning their task.
> All phases must proceed in dependency order per the Phase Overview and Dependency Graph.

---

*CivicAI — Master Architecture and Implementation Plan v2.0*
*Jurisdiction: Mangaluru, Karnataka, India*
*Budget: ₹0 / $0*

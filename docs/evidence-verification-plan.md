# CivicAI — AI Evidence Verification Architecture Plan

> **PLAN ONLY — No code changes until this plan is approved.**
> All sub-tasks marked `[ ] pending` until implementation begins.

---

## Top-Level Overview

**Goal**: Elevate CivicAI from "AI classifies an image" to "AI + backend together produce a credible,
explainable evidence verdict" for every citizen submission.

**Scope**: New evidence pipeline, decision-state model, duplicate/reopen logic, evidence scoring,
required DB schema additions, API changes, frontend changes.

**Non-scope (not touched)**:
- RTI flow
- RAG/knowledge base
- Auth/JWT
- Existing status state machine transitions (SUBMITTED → … → ARCHIVED)
- Existing authority routing (ADR-001 keyword matching)
- Admin status update API
- Storage buckets and signed-URL mechanism
- Supabase Realtime subscription
- Audit trigger
- Privacy redaction order — still mandatory FIRST

---

## 1. Current Architecture Assessment

### What works well
- Privacy pipeline (face + plate redaction) is correct and first in flow.
- YOLO + local RDD2022 road model provides genuine specialized road-surface detection.
- Groq vision + heuristic fallback covers non-road categories.
- Image validation and relevance gate correctly reject selfies and non-civic images.
- BLAKE3 hash for dedup advisory is correct.
- LLM description generation produces citizen-readable text.
- DB schema has geographic point column (`location GEOGRAPHY POINT 4326`) and GiST spatial index already in place.
- `ai_raw_response` JSONB is flexible storage for extended AI metadata.

### Current gaps
1. **Single-signal confidence**: `confidence = detection_confidence × category_weight` — this is only YOLO
   detection strength, not evidence quality. A 95% YOLO "car" class on a pothole image still produces
   a very low meaningful confidence number.
2. **No decision state**: The pipeline returns `category + confidence` only. There is no structured
   INVALID / INSUFFICIENT / DUPLICATE / REOPENED / VALID state.
3. **Duplicate is advisory-only, never surfaced to citizen**: `is_duplicate` is stored in JSONB but
   the citizen sees no message; no "linked evidence" relationship exists in the DB.
4. **No reopen detection**: If a pothole was RESOLVED and a new photo arrives at the same location,
   the system has no logic to detect recurrence.
5. **No location/freshness confidence**: GPS coordinates are stored but never scored; no freshness
   scoring on submission timestamp.
6. **No admin prioritization score**: Admin sees confidence % which is only YOLO weight — not useful.
7. **Category confidence vs evidence confidence conflated**: The current single `confidence` value
   mixes "how confident is the AI about the category" with "how much evidence supports this being real".

---

## 2. What Existing AI/CV Components to KEEP

| Component | Keep? | Role in new architecture |
|-----------|-------|--------------------------|
| Image validator (T2-2) | ✅ Keep as-is | Gate 1: input quality |
| Privacy redaction T2-3 + T2-4 | ✅ Keep as-is, first in flow | Mandatory before any external call |
| BLAKE3 hash (T2-7) | ✅ Keep as-is | Exact-duplicate detection signal |
| YOLO relevance gate (cv/relevance.py) | ✅ Keep as-is | Gate 2: reject selfies/non-civic |
| YOLOv8n COCO detection (cv/detection.py) | ✅ Keep as-is | Initial object detection for relevance and heuristic |
| Local RDD2022 road model (cv/road_damage.py) | ✅ Keep, wiring changes | Primary visual detector for road categories |
| Groq vision classifier (llm/groq_provider.py) | ✅ Keep, role narrowed | Visual detector for non-road categories + road fallback |
| Heuristic fallback (llm/fallback_provider.py) | ✅ Keep as limited fallback | Last-resort classification only; NOT evidence |
| LLM description generation | ✅ Keep as-is | Always runs; description uses final verified category |
| Authority routing (ADR-001) | ✅ Keep as-is | Unchanged |

---

## 3. What Should Be CHANGED

1. **AIResult** — add new fields: `decision_state`, `visual_confidence`, `category_confidence`,
   `location_confidence`, `freshness_confidence`, `evidence_score`, `severity`, `admin_priority`,
   `evidence_breakdown` (dict). Keep all existing fields for backward compat.

2. **Confidence computation** — replace single formula with multi-signal evidence scorer
   (`cv/evidence_scorer.py`, new file).

3. **Duplicate detection** — elevate from advisory to first-class decision state; add new DB table
   `report_links` to record the "supporting evidence" relationship. Citizen gets meaningful message.

4. **Pipeline output** — pipeline must return a `decision_state` (enum) in addition to category/confidence.

5. **Report creation service** — interpret `decision_state` to set appropriate DB status and link
   records when duplicate/reopen detected.

6. **API response (ReportOut)** — add `decision_state`, `evidence_score`, `citizen_message`,
   `linked_report_id`, `evidence_breakdown`.

7. **Frontend AI review stage** — show decision state and citizen message prominently.

8. **Admin dashboard** — show `decision_state` badge, `admin_priority` badge, `evidence_breakdown`.

---

## 4. What Should Be REWORKED

1. **run_ai_pipeline()** — must call the new evidence scorer and produce a `DecisionState`.
   Steps 3–4 (hash/duplicate) must be reworked into the evidence scorer so duplicate is a full
   decision state, not a boolean flag.

2. **Report creation flow (routers/reports.py)** — must interpret `decision_state`:
   - `INVALID_IMAGE` → return HTTP 422 (same as now for image errors)
   - `DUPLICATE_ACTIVE_REPORT` → create report, set initial status SUBMITTED,
     create `report_links` record, return special citizen message
   - `POSSIBLE_REOPENED_ISSUE` → create report with `is_reopened=True` flag, admin priority elevated
   - All others → create as now

3. **`ai_raw_response` JSONB** — must store full `evidence_breakdown` dict and `decision_state`
   so the admin can inspect why a score was assigned.

---

## 5. What Should NOT Be Touched

- RTI/RAG pipeline
- Auth/JWT/role system
- Supabase RLS policies (only additions for new tables)
- Status state machine transitions
- Audit trigger logic
- Authority seeded data / routing keyword logic (ADR-001)
- Storage buckets / signed URL generation
- Supabase Realtime subscription
- Report PATCH endpoint (citizen override)
- Admin status update endpoint
- Plate/face redaction internals

---

## 6. Final End-to-End AI/Evidence Architecture

```
Citizen submits photo + GPS + optional text
         │
         ▼
[GATE 1] Image validation (T2-2)
  • Format / size / magic bytes
  • Fails → HTTP 422 INVALID_IMAGE
         │
         ▼
[PRIVACY] Face + plate redaction (T2-3 + T2-4)
  • redacted_bytes produced here
  • ALL downstream AI receives redacted_bytes only
         │
         ▼
[GATE 2] Civic relevance gate (YOLO + cv/relevance.py)
  • Selfie/portrait → INVALID_IMAGE
  • Non-civic image → INVALID_IMAGE
         │
         ▼
[VISUAL] Civic visual classification
  Stage A: Local RDD2022 road model (redacted_bytes)
    → confident road result: visual_confidence set, category set, skip Groq
  Stage B (if not road or low conf): Groq vision / heuristic
    → category + category_confidence
  • Groq says invalid → INVALID_IMAGE
         │
         ▼
[HASH] BLAKE3 of validated_bytes → image_hash
         │
         ▼
[EVIDENCE SCORER] cv/evidence_scorer.py  ← NEW
  Inputs:
    • visual signal (category, visual_confidence, category_confidence)
    • GPS coordinates from submission
    • submission timestamp
    • image metadata (EXIF if present)
    • DB queries:
        – nearby active reports (same category, ≤ 100 m, status ∈ SUBMITTED/UNDER_REVIEW)
        – recently resolved reports (same category, ≤ 100 m, status=RESOLVED, ≤ 90 days)
        – exact hash duplicate check
  Computes:
    • visual_confidence    [0.0–1.0]
    • category_confidence  [0.0–1.0]
    • location_confidence  [0.0–1.0]  ← GPS quality + plausibility
    • freshness_confidence [0.0–1.0]  ← timestamp recency heuristic
    • duplicate_signal     (nearby_active_report | None)
    • reopen_signal        (nearby_resolved_report | None)
    • evidence_score       [0.0–1.0]  ← weighted combination
    • decision_state       DecisionState enum
    • admin_priority       HIGH / MEDIUM / LOW / REVIEW
    • evidence_breakdown   dict  ← explainable for admin
         │
         ▼
[AUTHORITY] Route to authority (ADR-001 — unchanged)
         │
         ▼
[LLM DESCRIPTION] generate_complaint_description()
  • Uses final verified category
  • Uses evidence_breakdown for context
  • Always runs (Groq → fallback)
         │
         ▼
AIResult returned
  (all existing fields + new evidence fields)
         │
         ▼
[REPORT CREATION] report_service.py
  • Stores report in DB
  • If DUPLICATE_ACTIVE_REPORT: creates report_links record
  • If POSSIBLE_REOPENED_ISSUE: sets is_reopened=True, elevates admin_priority
  • Returns ReportOut with decision_state + citizen_message
```

---

## 7. Exact Decision/State Model

```python
class DecisionState(str, Enum):
    INVALID_IMAGE           = "invalid_image"
    INSUFFICIENT_EVIDENCE   = "insufficient_evidence"
    DUPLICATE_ACTIVE_REPORT = "duplicate_active_report"
    POSSIBLE_REOPENED_ISSUE = "possible_reopened_issue"
    VALID_CIVIC_REPORT      = "valid_civic_report"
    NEEDS_ADMIN_REVIEW      = "needs_admin_review"
```

### State Assignment Rules

| State | When assigned |
|-------|--------------|
| `INVALID_IMAGE` | Image fails validation, relevance gate, or Groq says invalid |
| `INSUFFICIENT_EVIDENCE` | Passes visual gate but evidence_score < LOW_THRESHOLD (0.35); or location implausible; or visual classification is "other_civic" with low confidence |
| `DUPLICATE_ACTIVE_REPORT` | Nearby active report (same category, ≤ 100 m) exists AND evidence_score ≥ 0.30 |
| `POSSIBLE_REOPENED_ISSUE` | No active nearby duplicate BUT recently-resolved report (≤ 90 days) at same location, same category; new evidence suggests recurrence |
| `VALID_CIVIC_REPORT` | evidence_score ≥ HIGH_THRESHOLD (0.65); no active duplicate; consistent signals |
| `NEEDS_ADMIN_REVIEW` | evidence_score in [LOW_THRESHOLD, HIGH_THRESHOLD) AND not duplicate/reopen; ambiguous or conflicting signals |

### State → Report Behavior

| State | HTTP | DB Status | Action |
|-------|------|-----------|--------|
| `INVALID_IMAGE` | 422 | Not created | Error response to citizen |
| `INSUFFICIENT_EVIDENCE` | 200 | SUBMITTED | Created but flagged; low admin priority |
| `DUPLICATE_ACTIVE_REPORT` | 200 | SUBMITTED | Created + linked to existing report |
| `POSSIBLE_REOPENED_ISSUE` | 200 | SUBMITTED | Created with `is_reopened=True`; medium-high priority |
| `VALID_CIVIC_REPORT` | 200 | SUBMITTED | Normal creation; high priority |
| `NEEDS_ADMIN_REVIEW` | 200 | SUBMITTED | Created; flagged for manual review |

---

## 8. Duplicate Detection Architecture

### Detection Logic (in evidence_scorer.py)

```
Inputs: category, GPS coordinates, submission timestamp, image_hash

Step 1 — Exact hash check:
  SELECT id FROM reports WHERE image_hash = :hash AND status != 'ARCHIVED'
  → If found: DUPLICATE_ACTIVE_REPORT (exact same image resubmitted)

Step 2 — Nearby active report (same category):
  SELECT id, created_at, status, location
  FROM reports
  WHERE
    ST_DWithin(location, ST_MakePoint(:lng, :lat)::GEOGRAPHY, 100)  -- 100 metres
    AND ai_category = :category
    AND status IN ('SUBMITTED', 'UNDER_REVIEW')
  ORDER BY created_at DESC
  LIMIT 1
  → If found: DUPLICATE_ACTIVE_REPORT

Step 3 — Nearby recent active report (any civic category, same broad area):
  Same query with distance 50 m for stricter same-category match
  Used to compute duplicate_confidence component
```

**Distance thresholds** (configurable constants):
- Exact duplicate geo distance: 100 m (same category same status)
- Cross-category broad area: 50 m (only for confidence scoring, not for state)

### Database: `report_links` table (NEW)

```sql
CREATE TABLE report_links (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source_report_id   UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  target_report_id   UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  link_type     TEXT NOT NULL CHECK (link_type IN ('duplicate', 'supporting_evidence', 'reopened')),
  created_at    TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE (source_report_id, target_report_id)
);
```

- `source_report_id` = the new incoming report
- `target_report_id` = the existing active report it is linked to
- `link_type` = 'duplicate' for exact matches; 'supporting_evidence' for nearby active; 'reopened' for reopen case

**RLS**: Citizens SELECT where user_id matches either source or target report's user_id.
Admins SELECT all. Service_role INSERT/UPDATE.

**Index**: `idx_report_links_target` on `target_report_id` (to find all supporting evidence for a report).

### Citizen Message for Duplicate

```json
{
  "decision_state": "duplicate_active_report",
  "citizen_message": "An issue at or near this location has already been reported and is currently being reviewed. Your report has been recorded and linked as additional evidence to support the existing case.",
  "linked_report_id": "<uuid of active report>"
}
```

### Admin View for Duplicate

The admin dashboard report list should show a "Supporting evidence: N" count for reports that have
linked duplicates. Clicking shows the list of linked reports with their images and timestamps.

---

## 9. Recently-Resolved / Reopening Architecture

### Detection Logic (in evidence_scorer.py)

```
Step 1 — Find recently-resolved nearby reports:
  SELECT id, resolved_at, created_at, ai_category, location
  FROM reports
  WHERE
    ST_DWithin(location, ST_MakePoint(:lng, :lat)::GEOGRAPHY, 80)  -- 80 metres
    AND ai_category = :category
    AND status = 'RESOLVED'
    AND resolved_at > NOW() - INTERVAL '90 days'
  ORDER BY resolved_at DESC
  LIMIT 1
```

**Reopen decision criteria** (ALL of the following must be true):
1. A resolved report exists at ≤ 80 m for the same category within the last 90 days.
2. New submission's visual_confidence ≥ 0.40 (AI genuinely sees something).
3. New submission's freshness_confidence ≥ 0.50 (not a stale image upload).
4. No currently-active duplicate found (which takes precedence).

**Resolution time multiplier** for confidence:
- Resolved 0–30 days ago: reopen plausibility = 0.9 (very likely recurring)
- Resolved 31–60 days ago: reopen plausibility = 0.6
- Resolved 61–90 days ago: reopen plausibility = 0.3
- Resolved > 90 days ago: not considered a reopen; treated as a new independent issue

### citizen_message for Reopen

```json
{
  "decision_state": "possible_reopened_issue",
  "citizen_message": "A similar issue at this location was previously resolved. Your report suggests it may have recurred. It has been forwarded to the authority for review.",
  "linked_report_id": "<uuid of resolved report>"
}
```

The `report_links` record is created with `link_type = 'reopened'`.

### DB Changes for Reopen

Add `is_reopened BOOLEAN DEFAULT FALSE` to `reports` table.

When `decision_state = POSSIBLE_REOPENED_ISSUE`, set `reports.is_reopened = TRUE` at creation time.

Admin can see the "Reopened issue" badge and click through to the original resolved report.

---

## 10. Location Evidence Architecture

### What GPS CAN contribute (honest boundaries)

GPS from the mobile device is **corroborating evidence**, not proof:
- A legitimate citizen at a pothole location will produce GPS near the issue.
- A citizen uploading a random internet photo will have GPS at their home/office.
- GPS cannot prove the photo was taken there — only that the device reported those coordinates at
  submission time.

### Location Confidence Scoring

```
location_confidence = 0.0 (default)

Inputs available:
  - GPS accuracy radius (metres) from browser geolocation API (if provided)
  - latitude, longitude of submission
  - Whether GPS was provided at all (vs manual text entry only)

Scoring:
  if no GPS provided:
    location_confidence = 0.30  (text-only location; authority routing still possible)
  elif GPS accuracy > 50 m:
    location_confidence = 0.40  (imprecise GPS; plausible but low confidence)
  elif GPS accuracy ≤ 50 m:
    location_confidence = 0.70  (reasonable mobile GPS accuracy)
  elif GPS accuracy ≤ 20 m:
    location_confidence = 0.85  (precise GPS)

Plausibility check:
  If coordinates are outside Mangaluru bounding box:
    location_confidence × 0.1   (very low — location inconsistent with authority area)
```

**Mangaluru bounding box** (approx): lat 12.7–13.1, lng 74.7–75.1

The `location_confidence` should be stored as part of `evidence_breakdown` for audit purposes.

### DB Changes for Location

Add `gps_accuracy_metres REAL` to `reports` table (nullable — not always provided by browser).

The existing `location GEOGRAPHY POINT 4326` column is already correct and indexed.
The existing `address_text` (now: `reports.address_text`) is kept.

### API Change

`POST /api/v1/reports` multipart form should accept optional `gps_accuracy` field (float, metres).

---

## 11. Freshness Architecture

### What freshness CAN and CANNOT determine

**CAN**:
- When the report was submitted (server-side timestamp, authoritative).
- Whether EXIF metadata is present and contains a capture timestamp.
- Whether the EXIF timestamp is consistent with the submission timestamp.
- Whether nearby reports of the same issue have been recently filed (corroboration).

**CANNOT**:
- Verify the photo was taken today (EXIF is easily stripped or spoofed).
- Access real-time satellite/street-view imagery for comparison.
- Access government road inspection records.
- Prove the current state of the road from the image alone.

### Freshness Confidence Scoring

```
freshness_confidence = 0.50 (default — submission timestamp is always authoritative)

EXIF metadata check (if available after image validation):
  exif_timestamp = extract from validated image (before redaction)
  if exif_timestamp present:
    age_seconds = abs(submission_timestamp - exif_timestamp)
    if age_seconds < 3600:          # taken within 1 hour of submission
      freshness_confidence = 0.90
    elif age_seconds < 86400:       # taken within 24 hours
      freshness_confidence = 0.75
    elif age_seconds < 604800:      # within 7 days
      freshness_confidence = 0.55
    else:                           # older than 7 days
      freshness_confidence = 0.25   # possibly stale
  else:
    # No EXIF — use recent nearby corroboration
    nearby_recent_count = count reports submitted in last 7 days at ≤ 200 m same category
    if nearby_recent_count >= 2:
      freshness_confidence = 0.70   # corroborated by others recently
    elif nearby_recent_count == 1:
      freshness_confidence = 0.60
    # else remain 0.50
```

**EXIF extraction**: Done during Step 1 (before redaction strips EXIF), captured as metadata only —
the timestamp value is recorded in `evidence_breakdown`; the EXIF data itself is discarded before
storing the image (privacy).

**Important**: EXIF timestamps are NOT trusted as proof — they contribute to confidence scoring only.
The system must never claim "the image was taken at time X" as a verified fact.

---

## 12. Evidence Scoring Formula

### Component Scores

```
visual_confidence    = [0.0–1.0]  from road model or Groq vision
category_confidence  = [0.0–1.0]  model's certainty about the category
location_confidence  = [0.0–1.0]  GPS quality and plausibility
freshness_confidence = [0.0–1.0]  EXIF + corroboration heuristic
```

### Weights

```python
EVIDENCE_WEIGHTS = {
    "visual":    0.45,   # primary signal — what does the image show?
    "category":  0.20,   # how certain is the category assignment?
    "location":  0.20,   # how reliable and plausible is the GPS?
    "freshness": 0.15,   # how likely is this a current condition?
}
```

Rationale: visual evidence is the primary determinant (45%). Location and freshness are
corroborating signals but neither proves real-world conditions independently.

### Combination

```python
evidence_score = (
    visual_confidence    × EVIDENCE_WEIGHTS["visual"]    +
    category_confidence  × EVIDENCE_WEIGHTS["category"]  +
    location_confidence  × EVIDENCE_WEIGHTS["location"]  +
    freshness_confidence × EVIDENCE_WEIGHTS["freshness"]
)
# Clamp to [0.0, 1.0]
```

### Thresholds → DecisionState

```python
VALID_THRESHOLD       = 0.65   # evidence_score ≥ this → VALID_CIVIC_REPORT
REVIEW_THRESHOLD      = 0.35   # evidence_score ≥ this → NEEDS_ADMIN_REVIEW
                               # evidence_score <  this → INSUFFICIENT_EVIDENCE
```

### Admin Priority

```python
if decision_state == INVALID_IMAGE:
    admin_priority = "INVALID"
elif decision_state == DUPLICATE_ACTIVE_REPORT:
    admin_priority = "DUPLICATE"
elif decision_state == POSSIBLE_REOPENED_ISSUE:
    admin_priority = "HIGH"    # reopened issues deserve urgent attention
elif evidence_score >= 0.75:
    admin_priority = "HIGH"
elif evidence_score >= 0.50:
    admin_priority = "MEDIUM"
elif evidence_score >= REVIEW_THRESHOLD:
    admin_priority = "REVIEW"
else:
    admin_priority = "LOW"
```

### Severity

Severity is determined by the Groq vision / road model's assessment:
```
severity = "high"   if severity_score >= 0.75
severity = "medium" if severity_score >= 0.40
severity = "low"    otherwise
```

Severity is NOT used for `evidence_score` — severity describes the civic impact,
not the evidentiary strength.

### Evidence Breakdown (for admin explainability)

```json
{
  "visual_confidence": 0.82,
  "category_confidence": 0.91,
  "location_confidence": 0.70,
  "freshness_confidence": 0.55,
  "evidence_score": 0.78,
  "decision_state": "valid_civic_report",
  "admin_priority": "HIGH",
  "visual_source": "local_road_model",
  "raw_class": "D40",
  "yolo_class": "frisbee",
  "nearby_active_reports": 0,
  "nearby_resolved_reports": 1,
  "reopen_plausibility": 0.0,
  "gps_accuracy_m": 15.0,
  "exif_age_seconds": 1200,
  "freshness_note": "Image taken ~20 min before submission",
  "location_note": "GPS within Mangaluru bounding box; accuracy 15 m"
}
```

---

## 13. AI vs Deterministic Responsibility Split

| Decision | AI Responsible | Deterministic Responsible |
|----------|---------------|--------------------------|
| Image validity | ✅ validation rules (deterministic) | |
| Selfie detection | ✅ YOLO relevance gate | |
| Civic category | ✅ Road model / Groq vision | |
| Visual confidence | ✅ Model confidence output | |
| Description text | ✅ Groq / fallback template | |
| Duplicate detection | | ✅ DB geo + hash query |
| Reopen detection | | ✅ DB resolved report query |
| Location confidence | | ✅ GPS accuracy calculation |
| Freshness (EXIF age) | | ✅ Timestamp arithmetic |
| Freshness (corroboration) | | ✅ DB nearby-report count |
| Evidence score | | ✅ Weighted formula |
| Admin priority | | ✅ Threshold rules |
| Decision state | | ✅ Rule-based on score + signals |
| Authority routing | | ✅ ADR-001 keyword match |

**Key principle**: AI models provide visual understanding. Every actionable decision is made by
deterministic code using evidence from multiple sources. The AI model confidence is ONE input,
not THE decision.

---

## 14. Admin Workflow

### Report list view (enhanced)

Each report row should show:
- `admin_priority` badge: HIGH (red) / MEDIUM (yellow) / LOW (grey) / DUPLICATE / REVIEW / INVALID
- `decision_state` badge: human-readable label
- `evidence_score` as a percentage bar (replacing the raw `ai_confidence` percentage)
- Existing: status, category icon, authority, created_at

### Report detail view (enhanced)

Evidence breakdown panel (collapsible):
```
📷 Visual Evidence:  82% (local road model — D40 pothole)
📍 Location:         70% (GPS 15 m accuracy — within city bounds)
🕐 Freshness:        55% (no EXIF; no recent nearby reports)
🏷 Category:         91% (pothole — high model certainty)
━━━━━━━━━━━━━━━━━━━
Overall Evidence:    78% → VALID CIVIC REPORT
Priority:            HIGH
```

For duplicate reports:
```
🔗 Linked to report #1234 (submitted 2 days ago, currently UNDER_REVIEW)
   Supporting evidence: this submission provides additional confirmation
```

### Admin does NOT need to manually review
- `INVALID_IMAGE` — auto-rejected (never stored as a report; 422 returned to citizen)
- `DUPLICATE_ACTIVE_REPORT` with low additional value — linked and deprioritized

### Admin MUST review
- `NEEDS_ADMIN_REVIEW` — ambiguous evidence; admin makes final call
- `POSSIBLE_REOPENED_ISSUE` — admin confirms whether the issue has actually recurred

---

## 15. Citizen Workflow

### On submission

Citizen submits photo + GPS (or manual address) + optional text.

### AI review stage (Stage 2 in current flow) — enhanced

Show `decision_state` message prominently above the AI result:

| Decision State | Citizen Message |
|---------------|----------------|
| `VALID_CIVIC_REPORT` | "Your report has been verified and submitted. An authority will review it shortly." |
| `NEEDS_ADMIN_REVIEW` | "Your report has been submitted for manual review. An authority representative will assess it." |
| `INSUFFICIENT_EVIDENCE` | "The system could not clearly identify a civic issue in the submitted image or location. Your report has been submitted but may need additional information. You can edit the category or description below." |
| `DUPLICATE_ACTIVE_REPORT` | "An issue at or near this location has already been reported and is currently being reviewed. Your report has been linked as additional evidence." |
| `POSSIBLE_REOPENED_ISSUE` | "A similar issue at this location was previously resolved. Your new report suggests it may have recurred and has been forwarded for urgent review." |

**The citizen still sees the AI category, description, authority recommendation, and can override.**
**The citizen is NOT shown the internal evidence scores or breakdown.**

### For duplicates specifically

The citizen sees:
- Their own report's AI result (category, description, authority)
- The message above
- A link to the existing active report (read-only view)

---

## 16. Required DB/Schema Changes

### New fields on `reports` table

```sql
ALTER TABLE reports ADD COLUMN evidence_score      REAL;
ALTER TABLE reports ADD COLUMN decision_state      TEXT;
ALTER TABLE reports ADD COLUMN admin_priority      TEXT DEFAULT 'LOW';
ALTER TABLE reports ADD COLUMN is_reopened         BOOLEAN DEFAULT FALSE;
ALTER TABLE reports ADD COLUMN gps_accuracy_metres REAL;    -- nullable
ALTER TABLE reports ADD COLUMN severity            TEXT;    -- 'low'/'medium'/'high'/null
ALTER TABLE reports ADD COLUMN linked_report_id    UUID REFERENCES reports(id);
  -- shortcut FK: populated when decision_state = duplicate_active_report or possible_reopened_issue
```

> Note: `ai_raw_response` JSONB already exists and will continue to store
> the full `evidence_breakdown` dict for audit purposes.

### New `report_links` table

```sql
CREATE TABLE report_links (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_report_id   UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  target_report_id   UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  link_type          TEXT NOT NULL CHECK (link_type IN ('duplicate','supporting_evidence','reopened')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_report_id, target_report_id)
);

CREATE INDEX idx_report_links_target ON report_links(target_report_id);
CREATE INDEX idx_report_links_source ON report_links(source_report_id);
```

### RLS for `report_links`

```sql
-- Citizens can see links involving their own reports
CREATE POLICY "citizen_select_own_links" ON report_links FOR SELECT TO authenticated
  USING (
    source_report_id IN (SELECT id FROM reports WHERE user_id = auth.uid())
    OR
    target_report_id IN (SELECT id FROM reports WHERE user_id = auth.uid())
  );
-- Admins see all
CREATE POLICY "admin_select_all_links" ON report_links FOR SELECT TO authenticated
  USING (is_admin());
-- Service role inserts
```

### Index for geographic duplicate search (already exists!)

`idx_reports_location` (GiST on `reports.location`) — already present in `003_indexes.sql`.
The PostGIS `ST_DWithin` queries in evidence_scorer.py will use this index directly.

### No migration needed for

- Existing columns: `location`, `image_hash`, `ai_category`, `ai_confidence`, `ai_raw_response`,
  `address_text`, `image_original_path`, `image_redacted_path`, `status`, `rejection_reason`
- All existing status transitions
- All RLS for existing tables (only additions)

---

## 17. Required API/Backend Changes

### New / changed backend files

| File | Change |
|------|--------|
| `cv/evidence_scorer.py` | NEW — multi-signal evidence scorer; returns `EvidenceResult` dataclass |
| `cv/pipeline.py` | Add evidence scorer call; add new AIResult fields; re-wire duplicate detection |
| `schemas/report.py` | Add `DecisionState` enum; extend `ReportOut` with new fields; add `gps_accuracy` to `ReportCreate` |
| `services/report_service.py` | Interpret `decision_state`; create `report_links` on duplicate/reopen |
| `db/repositories/report_repo.py` | New DB queries: ST_DWithin nearby active, nearby resolved, insert report_links |
| `routers/reports.py` | Accept `gps_accuracy` field; return `decision_state` + `citizen_message` in response |
| `routers/admin.py` | New endpoint: `GET /api/v1/admin/reports/{id}/evidence` to return full evidence breakdown |

### API changes to `POST /api/v1/reports`

**Request** (new optional field):
```
gps_accuracy: float (optional, metres)
```

**Response** (`ReportOut`) — new fields:
```json
{
  "decision_state": "valid_civic_report",
  "evidence_score": 0.78,
  "admin_priority": "HIGH",
  "severity": "high",
  "citizen_message": "Your report has been verified and submitted.",
  "linked_report_id": null,
  "evidence_breakdown": null  // always null in citizen-facing response; only for admin
}
```

### New admin API endpoint

```
GET /api/v1/admin/reports/{id}/evidence
  → Returns full evidence_breakdown JSONB from ai_raw_response
  → Admin auth required
```

### `run_ai_pipeline()` signature (no breaking change)

```python
async def run_ai_pipeline(
    image_bytes: bytes,
    location: str = "",
    address: str = "",
    claimed_mime: str = "",
    existing_hashes: Optional[list] = None,
    gps_accuracy: Optional[float] = None,   # NEW optional
    submission_timestamp: Optional[datetime] = None,  # NEW optional
) -> AIResult
```

---

## 18. Required Frontend Changes

### Report creation page (`frontend/app/report/new/page.tsx`)

1. **GPS accuracy** — when calling browser geolocation API, capture `accuracy` from
   `GeolocationPosition.coords.accuracy` and include it in the POST request.

2. **AI review stage** — add `decision_state` message banner above AI result panel:
   - Use decision_state from API response to select the appropriate citizen_message.
   - Show `linked_report_id` as a link for duplicate/reopen states.
   - Do NOT show `evidence_score` or `evidence_breakdown` to citizens.

3. **Confidence display** — replace the current raw `confidence` percentage with `evidence_score`
   percentage. Rename label from "AI Confidence" to "Evidence Strength".

### Admin dashboard (`frontend/app/admin/page.tsx`)

1. **Report list** — add `admin_priority` badge column and `decision_state` badge column.

2. **Report detail** — add collapsible "Evidence Breakdown" panel showing the stored
   `evidence_breakdown` from `ai_raw_response`.

3. **Linked reports** — for reports with `linked_report_id`, show a "View linked report" button.

4. **Supporting evidence count** — for reports that are targets of duplicates, show
   "N supporting reports" count (from `report_links` table).

5. **Filter by priority** — add admin_priority filter to the report list.

---

## 19. Privacy/Data-Flow Guarantees

These invariants are UNCHANGED and ENFORCED:

1. `original image bytes` are NEVER stored publicly — only `validated_bytes` go to `report-originals`.
2. `redacted_bytes` (faces + plates blurred) go to `report-redacted`.
3. ALL downstream AI models receive `redacted_bytes` only — this includes the local road model,
   Groq vision, and YOLO. Validated (pre-redaction) bytes are used ONLY for hash computation.
4. EXIF extraction (for freshness scoring) reads the EXIF timestamp only from `validated_bytes`
   before redaction strips it; the timestamp value is recorded as a number, not the raw EXIF data.
5. `evidence_breakdown` is stored in `ai_raw_response` JSONB — this contains no image bytes,
   no raw model weights, no PII.
6. Signed URLs continue to have 15-minute expiry; only `report-redacted` bucket is accessible.
7. `INVALID_IMAGE` decisions never create a DB report record — no storage of invalid images.

```
Raw bytes
  ↓
validate → validated_bytes
  ├── EXIF timestamp extracted (number only, stored in breakdown)  ← NEW
  ↓
redact → redacted_bytes
  ↓
[ALL AI/CV steps receive redacted_bytes]
  ├── YOLO, road model, Groq vision
  ↓
hash(validated_bytes) → image_hash
  ↓
Store: validated_bytes → report-originals (service_role only)
Store: redacted_bytes  → report-redacted  (signed URL)
```

---

## 20. Failure/Fallback Behavior

| Failure Mode | Behavior |
|-------------|----------|
| Local road model unavailable (no HF Hub) | Fall through to Groq vision; evidence_score reduced |
| Groq vision unavailable / no API key | Use heuristic fallback; visual_confidence capped at 0.55 |
| Heuristic returns "other_civic" | category_confidence = 0.30; likely NEEDS_ADMIN_REVIEW |
| PostGIS geo query fails (DB error) | Log warning; set duplicate_signal=None; location_confidence unchanged |
| GPS not provided by citizen | location_confidence = 0.30; no geo queries possible |
| EXIF extraction fails | freshness_confidence = 0.50 default; no penalty |
| evidence_scorer raises unexpected exception | Log error; set evidence_score = 0.0; decision_state = NEEDS_ADMIN_REVIEW |
| report_links INSERT fails | Log warning; report still created; link not recorded |

The application MUST NOT crash or return HTTP 500 due to evidence scorer failures.

---

## 21. Testing Strategy

### New test file: `backend/tests/test_evidence_scorer.py`

Must cover:
- Evidence score formula (weights, clamping)
- Decision state assignment at all thresholds
- Duplicate detection path (mock DB returns nearby active report)
- Reopen detection path (mock DB returns resolved report)
- No GPS provided → location_confidence = 0.30
- EXIF timestamp present and consistent → high freshness_confidence
- EXIF older than 7 days → low freshness_confidence
- All failure modes (DB error, EXIF failure, etc.)
- Evidence breakdown dict has all required keys

### Updated tests

- `test_pipeline.py` — add tests for new AIResult fields (decision_state, evidence_score, etc.)
- `test_reports.py` — add tests for:
  - Duplicate creates report_links record
  - Reopen sets is_reopened=True
  - INVALID_IMAGE never creates DB record
  - gps_accuracy field accepted in POST

### New test file: `backend/tests/test_report_links.py`

Must cover RLS: citizen can see own links; cannot see others'; admin sees all.

---

## 22. Performance Considerations

1. **ST_DWithin queries**: The existing GiST spatial index on `reports.location` is already in place.
   Two PostGIS queries per submission (nearby active + nearby resolved) should be fast with the index.

2. **Evidence scorer is synchronous CPU work**: No additional model loading. Runs inline in async
   pipeline. Expected time: < 5 ms.

3. **EXIF extraction**: PIL EXIF read is fast (< 1 ms). No additional dependency required.

4. **No additional AI models**: The new architecture does NOT add any new model. Existing models
   remain lazy-loaded.

5. **report_links INSERT**: O(1) DB write on duplicate detection — negligible.

6. **Pipeline memory**: No change to model memory footprint; evidence scorer is pure Python/math.

---

## 23. Security/RLS Considerations

1. **report_links RLS**: Citizens can only see links involving their own reports. They cannot
   enumerate other citizens' report IDs through link lookups.

2. **evidence_breakdown in API response**: `evidence_breakdown` is NEVER returned to citizen-facing
   API responses (only `citizen_message`). It is only accessible via the admin-authenticated
   `GET /api/v1/admin/reports/{id}/evidence` endpoint.

3. **admin_priority**: Not returned to citizens. Appears only in admin list/detail views.

4. **GPS accuracy**: Stored as a number. No device fingerprinting.

5. **Bounding box check**: The Mangaluru bounding box check is a confidence heuristic, NOT a
   rejection criterion. Submissions outside the box still proceed; location_confidence is lowered.

6. **Decision state INVALID_IMAGE**: No DB record created, no storage write. No PII leak.

7. **No new external services**: Evidence scoring is entirely internal. No new APIs. No new
   external models. No calls to government data sources.

---

## 24. Exact Files Likely to Change

### New files
- `backend/cv/evidence_scorer.py`
- `backend/tests/test_evidence_scorer.py`
- `backend/tests/test_report_links.py`
- `supabase/migrations/010_evidence_fields.sql`
- `supabase/migrations/011_report_links.sql`

### Modified files
- `backend/cv/pipeline.py` — integrate evidence scorer; add new AIResult fields
- `backend/schemas/report.py` — add DecisionState enum; extend ReportOut; add gps_accuracy
- `backend/services/report_service.py` — interpret decision_state; create report_links
- `backend/db/repositories/report_repo.py` — new queries (ST_DWithin nearby, resolved nearby, insert link)
- `backend/routers/reports.py` — accept gps_accuracy; return new response fields
- `backend/routers/admin.py` — new evidence endpoint
- `backend/tests/test_pipeline.py` — add tests for new AIResult fields
- `backend/tests/test_reports.py` — add duplicate/reopen integration tests
- `frontend/app/report/new/page.tsx` — capture GPS accuracy; show decision_state message
- `frontend/app/admin/page.tsx` — add priority badge; evidence breakdown panel; linked reports

### NOT modified
- `backend/cv/road_damage.py` — unchanged
- `backend/cv/detection.py` — unchanged
- `backend/cv/privacy.py` — unchanged
- `backend/cv/relevance.py` — unchanged
- `backend/cv/image_validator.py` — unchanged
- `backend/llm/groq_provider.py` — unchanged
- `backend/llm/fallback_provider.py` — unchanged
- `backend/services/llm_service.py` — unchanged
- `backend/services/authority_service.py` — unchanged
- `supabase/migrations/001_enums.sql` through `009_storage_buckets.sql` — NOT modified (only new migrations added)

---

## 25. Migration Sequence

```
010_evidence_fields.sql
  - ALTER TABLE reports ADD COLUMN evidence_score REAL
  - ALTER TABLE reports ADD COLUMN decision_state TEXT
  - ALTER TABLE reports ADD COLUMN admin_priority TEXT DEFAULT 'LOW'
  - ALTER TABLE reports ADD COLUMN is_reopened BOOLEAN DEFAULT FALSE
  - ALTER TABLE reports ADD COLUMN gps_accuracy_metres REAL
  - ALTER TABLE reports ADD COLUMN severity TEXT
  - ALTER TABLE reports ADD COLUMN linked_report_id UUID REFERENCES reports(id)
  - CREATE INDEX idx_reports_decision_state ON reports(decision_state)
  - CREATE INDEX idx_reports_admin_priority ON reports(admin_priority)

011_report_links.sql
  - CREATE TABLE report_links (...)
  - CREATE INDEX idx_report_links_target ON report_links(target_report_id)
  - CREATE INDEX idx_report_links_source ON report_links(source_report_id)
  - RLS policies for report_links

012_realtime_links.sql  (optional — if admin needs realtime on report_links)
  - ALTER PUBLICATION supabase_realtime ADD TABLE report_links
```

Existing data: All existing reports will have `evidence_score = NULL`, `decision_state = NULL`,
`admin_priority = 'LOW'`. This is safe — existing admin workflow is unaffected by NULL columns.

---

## 26. Risks and Limitations

### Technical risks
- **PostGIS availability**: The existing migrations already create the spatial index and use
  `GEOGRAPHY POINT` type, so PostGIS is assumed available. If not, evidence scorer must handle
  geo query failures gracefully (fallback to no duplicate detection).
- **ST_DWithin distance units**: When using GEOGRAPHY type, ST_DWithin uses metres directly —
  no unit conversion required. Must be verified during implementation.

### Evidence limitations (HONEST ASSESSMENT)

> **CAN the system verify current real-world road conditions?**
>
> **NO — not fully.** The system CAN verify:
> - That an uploaded image appears to show a specific civic problem (AI visual classification).
> - That a mobile device reported GPS coordinates near a known civic area (location corroboration).
> - That the image was recently captured (if EXIF is present and consistent).
> - That other citizens have recently reported similar issues in the same area (corroboration).
> - That a matching issue has not already been flagged as active (duplicate prevention).
>
> The system CANNOT verify:
> - That the photo was taken at the reported GPS location (GPS spoofing is possible).
> - That the civic issue still exists at the time of review (issue may be resolved between submission and admin review).
> - That the image was not taken from a previous session, a social media post, or another device.
> - Real-time road condition from any external authoritative source.
> - Government maintenance records or inspection schedules.
>
> These are fundamental epistemic limits of a mobile-reporting system without trusted external data sources.
> The architecture is honest about these limits — the evidence score is explicitly a "confidence in
> the evidence presented", not "certainty that the road currently has a pothole."

### Product risks
- **False INSUFFICIENT_EVIDENCE** for legitimate reports: A genuine pothole submitted with text-only
  location and no EXIF will score ~0.55–0.65, potentially landing in NEEDS_ADMIN_REVIEW rather than
  VALID. This is conservative by design.
- **Threshold calibration**: `VALID_THRESHOLD=0.65` and `REVIEW_THRESHOLD=0.35` are starting values
  that will need tuning based on real submission data.
- **Duplicate geo threshold (100 m)**: Urban potholes can appear within 100 m of each other. False
  duplicate matches are possible. The admin can override by changing the linked report's status.

---

## 27. Recommended Implementation Order

Each sub-task is independent and reviewable:

### Sub-task 1 — Evidence scorer core
**Status**: `[ ] pending`
- Create `backend/cv/evidence_scorer.py` with `EvidenceResult` dataclass and scoring formula
- Create `backend/tests/test_evidence_scorer.py` with unit tests
- No pipeline changes yet

### Sub-task 2 — DB migrations
**Status**: `[ ] pending`
- Write `supabase/migrations/010_evidence_fields.sql` (new report columns)
- Write `supabase/migrations/011_report_links.sql` (report_links table + RLS)
- Write tests for RLS policies

### Sub-task 3 — Pipeline integration
**Status**: `[ ] pending`
- Integrate evidence scorer into `backend/cv/pipeline.py`
- Add new fields to `AIResult` dataclass
- Wire geo queries into evidence scorer (requires report_repo changes)
- Update `backend/tests/test_pipeline.py`

### Sub-task 4 — Backend service / API
**Status**: `[ ] pending`
- Update `backend/schemas/report.py` (DecisionState enum, new ReportOut fields)
- Update `backend/db/repositories/report_repo.py` (new geo queries, insert report_links)
- Update `backend/services/report_service.py` (interpret decision_state, create links)
- Update `backend/routers/reports.py` (accept gps_accuracy, return new fields)
- Update `backend/routers/admin.py` (evidence endpoint)
- Update `backend/tests/test_reports.py`

### Sub-task 5 — Frontend
**Status**: `[ ] pending`
- Update `frontend/app/report/new/page.tsx` (GPS accuracy capture, decision_state message)
- Update `frontend/app/admin/page.tsx` (priority badge, evidence breakdown, linked reports)
- TypeScript typecheck + Next.js build must pass

---

## Appendix: Full Field Reference

### AIResult (updated)
```python
@dataclass
class AIResult:
    # Existing fields (unchanged)
    redacted_image_bytes: bytes
    validated_image_bytes: bytes
    category: IssueCategory
    confidence: float               # kept for backward compat; = evidence_score
    authority_recommendation: str
    authority_id: str
    description: str
    image_hash: str
    is_duplicate: bool              # kept for backward compat
    duplicate_report_id: Optional[str]
    llm_provider_used: str
    yolo_class: str
    raw_detection_confidence: float
    match_reason: str

    # New fields
    decision_state: DecisionState   # the primary output
    visual_confidence: float        # from AI model (road model or Groq)
    category_confidence: float      # model certainty about category
    location_confidence: float      # GPS quality + plausibility
    freshness_confidence: float     # timestamp/EXIF heuristic
    evidence_score: float           # weighted combination [0.0–1.0]
    severity: Optional[str]         # 'low' / 'medium' / 'high' / None
    admin_priority: str             # HIGH / MEDIUM / LOW / REVIEW / DUPLICATE / INVALID
    evidence_breakdown: dict        # full explainability dict for admin
    citizen_message: str            # human-readable decision message for citizen
    linked_report_id: Optional[str] # for duplicate/reopen states
```

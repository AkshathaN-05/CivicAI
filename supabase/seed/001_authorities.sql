-- =============================================================================
-- Seed 001 — Authority Records
-- Task: T1-5 (Phase 1)
-- Canonical plan: Part A §12 (ADR-001), §38 item 7
-- Depends on: 004_rls.sql (authorities table must exist and RLS must be active)
-- Source of truth: backend/data/mangaluru_authorities.json (IMMUTABLE)
-- Idempotent: ON CONFLICT (id) DO NOTHING
-- ADR-001: categories + area_text only. No ward_range, no ward integers,
--          no routing geometry, no GeoJSON.
-- All 7 authority records inserted exactly as they appear in the JSON source.
-- =============================================================================

INSERT INTO public.authorities
    (id, name, short_name, categories, area_text, contact_email, phone)
VALUES
    (
        'auth-001',
        'Mangaluru City Corporation (MCC)',
        'MCC',
        ARRAY[
            'pothole',
            'road_damage',
            'garbage_overflow',
            'broken_streetlight',
            'illegal_construction',
            'open_drain',
            'other'
        ]::issue_category[],
        'Mangaluru city limits, Kadri, Hampankatta, Lalbagh, Balmatta, Kodialbail, Urwa, Kankanady, Attavar, Bejai, Bunts Hostel, Bikarnakatte',
        'commissioner@mangalurumahanagara.in',
        '0824-2220055'
    ),
    (
        'auth-002',
        'Mangaluru City Corporation — North Zone',
        'MCC North',
        ARRAY[
            'pothole',
            'road_damage',
            'garbage_overflow',
            'broken_streetlight'
        ]::issue_category[],
        'Derebail, Kuloor, Nanthoor, Bondel, Kavoor, Kulayi, Katipalla, Surathkal',
        'northzone@mangalurumahanagara.in',
        '0824-2220066'
    ),
    (
        'auth-003',
        'Mangaluru Water Works Department',
        'MWWD',
        ARRAY[
            'water_supply',
            'sewage'
        ]::issue_category[],
        'Mangaluru city, Kuloor, Derebail, Bondel, Kadri, Attavar, Kankanady, Bejai, Urwa, Hampankatta',
        'waterworks@mangalurumahanagara.in',
        '0824-2424444'
    ),
    (
        'auth-004',
        'National Highways Authority of India — Mangaluru',
        'NHAI Mangaluru',
        ARRAY[
            'pothole',
            'road_damage'
        ]::issue_category[],
        'NH 75, NH 66, Pumpwell Circle, Bunts Hostel junction, Padil, Vamanjoor, Thokkottu, Surathkal, Bajpe',
        'mangaluru@nhai.org',
        '0824-2452001'
    ),
    (
        'auth-005',
        'MESCOM (Electricity Supply Company)',
        'MESCOM',
        ARRAY[
            'broken_streetlight'
        ]::issue_category[],
        'Mangaluru, Kadri, Hampankatta, Kodialbail, Bikarnakatte, Surathkal, Kuloor, Derebail, Bondel, Kankanady, Bejai',
        'mangaluru@mescom.in',
        '1912'
    ),
    (
        'auth-006',
        'Mangaluru Urban Development Authority (MUDA)',
        'MUDA',
        ARRAY[
            'illegal_construction',
            'other'
        ]::issue_category[],
        'Mangaluru urban agglomeration, Derebail, Kuloor, Nanthoor, Kavoor, Bikarnakatte, Vamanjoor, Mulky, Moodbidri',
        'commissioner@muda.gov.in',
        '0824-2454321'
    ),
    (
        'auth-007',
        'MCC Drainage Division',
        'MCC Drainage',
        ARRAY[
            'waterlogging',
            'open_drain',
            'sewage'
        ]::issue_category[],
        'Mangaluru city, Hampankatta, Balmatta, Kadri, Kodialbail, Bejai, Urwa, Kavoor, Derebail, Kankanady',
        'drainage@mangalurumahanagara.in',
        '0824-2220077'
    )
ON CONFLICT (id) DO NOTHING;

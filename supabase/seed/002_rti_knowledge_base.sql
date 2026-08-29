-- =============================================================================
-- Seed 002 — RTI Knowledge Base
-- Task: T2-13 (Phase 2)
-- Canonical plan: Part A §10, Part B §Knowledge Base Content (T2-13)
-- Depends on: 002_tables.sql (rti_knowledge_base table must exist)
-- Idempotent: ON CONFLICT (id) DO NOTHING
--
-- Content categories (architecture Part B §Knowledge Base Content):
--   1. RTI Act 2005 — key sections: Section 6 (application),
--      Section 7 (timeline), Section 19 (appeal)
--   2. Mangaluru City Corporation complaint procedure summary
--   3. Karnataka Municipal Corporations Act relevant provisions
--   4. Sample RTI letter format
--   5. BBMP/MCC contact hierarchy for escalation
--
-- Embedding: NULL — model runs locally (T2-12 embedder.py).
--   Rows are inserted without embeddings so this seed works in all
--   environments (keyword-only fallback active until embeddings are computed
--   by the ingestion script).  The vector_store.search() function skips rows
--   WHERE embedding IS NULL, so keyword_search() picks them up instead.
--
-- Chunking: each INSERT is a pre-chunked segment (≤512 tokens each).
--   The chunker.py (T2-13) is used when re-ingesting with embeddings.
-- =============================================================================

INSERT INTO public.rti_knowledge_base
    (id, title, content, embedding, source_url)
VALUES

-- ---------------------------------------------------------------------------
-- Category 1: RTI Act 2005 — Section 6 (Application procedure)
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000001'::uuid,
    'RTI Act 2005 — Section 6: How to Request Information',
    'Section 6 of the Right to Information Act 2005 governs the procedure for making an RTI application. A citizen who desires to obtain any information under this Act shall make a request in writing or through electronic means in English or Hindi or in the official language of the area, to the Public Information Officer (PIO) of the concerned public authority. The request should specify the particulars of the information sought. No reason is required to be given for requesting the information. The application must be accompanied by the prescribed fee (currently Rs. 10 for central government bodies). Below Poverty Line (BPL) applicants are exempted from paying the application fee.',
    NULL,
    'https://rti.gov.in/rti-act.pdf'
),
(
    '00000000-0000-0000-0000-000000000002'::uuid,
    'RTI Act 2005 — Section 6: PIO Responsibilities and Transfer',
    'The Public Information Officer (PIO) is responsible for providing information to a person who makes a request under Section 6. If the information requested concerns another public authority, the PIO shall transfer the application to that authority within 5 days of receipt of the application. In case of a transfer, the PIO must inform the applicant about the transfer. Each public authority must designate a Central Public Information Officer (CPIO) at the central level or a State Public Information Officer (SPIO) at the state level. The PIO must provide the information within 30 days of the receipt of the application.',
    NULL,
    'https://rti.gov.in/rti-act.pdf'
),

-- ---------------------------------------------------------------------------
-- Category 1: RTI Act 2005 — Section 7 (Timeline and disposal)
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000003'::uuid,
    'RTI Act 2005 — Section 7: Time Limit for Providing Information',
    'Section 7 of the RTI Act 2005 specifies the time limits within which the Public Information Officer must provide the requested information. The PIO must provide the information within 30 days of the receipt of the request. If the information sought concerns the life or liberty of a person, the information must be provided within 48 hours. If the PIO fails to provide the information within the prescribed period, the request is deemed to have been refused. In such a case, the applicant may file a first appeal under Section 19 of the Act.',
    NULL,
    'https://rti.gov.in/rti-act.pdf'
),
(
    '00000000-0000-0000-0000-000000000004'::uuid,
    'RTI Act 2005 — Section 7: Fees, Rejection and Partial Disclosure',
    'Under Section 7, if the information sought is voluminous or requires substantial compilation, the PIO may charge additional fees for providing the information, including photocopying charges and inspection fees. The PIO must inform the applicant about the additional fees within 5 days of receiving the application. If the PIO decides to reject the information request, the PIO must communicate the reasons for rejection, the period within which an appeal against such rejection may be preferred, and the particulars of the Appellate Authority. Partial information may be provided after severing the exempt portions.',
    NULL,
    'https://rti.gov.in/rti-act.pdf'
),

-- ---------------------------------------------------------------------------
-- Category 1: RTI Act 2005 — Section 19 (Appeal procedure)
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000005'::uuid,
    'RTI Act 2005 — Section 19: First Appeal',
    'Section 19(1) of the RTI Act 2005 provides that any person who does not receive a decision within the time specified, or is aggrieved by a decision of the Central Public Information Officer or State Public Information Officer, may prefer an appeal to an officer who is senior in rank to the PIO in the concerned public authority. The first appeal must be filed within 30 days of the expiry of the prescribed period or from the receipt of the decision. The Appellate Authority must dispose of the appeal within 30 days of receipt, which may be extended to 45 days for reasons to be recorded in writing.',
    NULL,
    'https://rti.gov.in/rti-act.pdf'
),
(
    '00000000-0000-0000-0000-000000000006'::uuid,
    'RTI Act 2005 — Section 19: Second Appeal to Information Commission',
    'Section 19(3) of the RTI Act 2005 allows a second appeal to the Central Information Commission (CIC) or State Information Commission (SIC) if the first appeal is not disposed of within the prescribed time limit or the applicant is not satisfied with the decision. The second appeal must be filed within 90 days of the date on which the decision should have been made or was actually received. The Information Commission may impose penalties on the PIO for delay, refusal, or providing false information. The Commission may also award compensation to the applicant. The penalty can be up to Rs. 25,000.',
    NULL,
    'https://rti.gov.in/rti-act.pdf'
),

-- ---------------------------------------------------------------------------
-- Category 2: Mangaluru City Corporation complaint procedure
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000007'::uuid,
    'Mangaluru City Corporation — Civic Complaint Procedure',
    'The Mangaluru City Corporation (MCC) is the primary local body responsible for civic amenities in Mangaluru. Citizens can submit complaints about potholes, road damage, garbage overflow, broken streetlights, open drains, waterlogging, illegal construction, water supply failures, and sewage problems. Complaints can be submitted through the MCC online portal, in person at the MCC commissioner''s office at Lalbagh, or by calling the helpline at 0824-2220055. Each complaint is assigned a reference number. The MCC is legally required to acknowledge and respond to complaints within 30 days under the Karnataka Municipalities Act.',
    NULL,
    'https://mangalurumahanagara.in'
),
(
    '00000000-0000-0000-0000-000000000008'::uuid,
    'Mangaluru City Corporation — Complaint Categories and Responsible Departments',
    'MCC divides civic complaints into department-specific categories. Road potholes and road damage: Roads and Infrastructure Department. Garbage overflow and solid waste: Solid Waste Management Department. Broken streetlights: Electrical and Street Lighting Department. Open drains and waterlogging: Drainage and Sewerage Department. Illegal construction: Town Planning Department. Water supply failures: Mangaluru Water Works Department (MWWD). Each department has a designated nodal officer for complaints. For national highway issues, complaints should be directed to the National Highways Authority of India (NHAI) Mangaluru office.',
    NULL,
    'https://mangalurumahanagara.in'
),
(
    '00000000-0000-0000-0000-000000000009'::uuid,
    'Mangaluru City Corporation — Complaint Escalation and No-Response Procedure',
    'If a civic complaint submitted to the Mangaluru City Corporation receives no response within 30 days, the citizen has the following escalation options. First escalation: contact the relevant department head directly by phone or email. Second escalation: submit a written complaint to the MCC Commissioner''s office requesting status update. Third escalation: file an RTI application under Section 6 of the RTI Act 2005 requesting information about the complaint status, actions taken, and timeline. The RTI application should be addressed to the Public Information Officer of the Mangaluru City Corporation. If no RTI response is received within 30 days, a first appeal can be filed.',
    NULL,
    'https://mangalurumahanagara.in'
),

-- ---------------------------------------------------------------------------
-- Category 3: Karnataka Municipal Corporations Act relevant provisions
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000010'::uuid,
    'Karnataka Municipal Corporations Act — Civic Duty and Complaint Rights',
    'The Karnataka Municipal Corporations Act 1976 (as amended) governs municipal corporations in Karnataka including Mangaluru City Corporation. Under this Act, the municipal corporation is obligated to maintain roads, drains, streetlights, sanitation, water supply, and other civic amenities within its jurisdiction. Section 58 of the Act empowers citizens to petition the corporation for remedial action on civic grievances. Section 59 requires the corporation to respond to petitions within a reasonable time. Failure to maintain civic amenities may constitute negligence under the Act.',
    NULL,
    'https://dpal.kar.nic.in'
),
(
    '00000000-0000-0000-0000-000000000011'::uuid,
    'Karnataka Municipal Corporations Act — Penalties for Non-Performance',
    'Under the Karnataka Municipal Corporations Act 1976, if the corporation fails to perform its mandatory duties and a citizen suffers damages, the citizen may seek redress through the Karnataka High Court or through the Lokayukta. The Karnataka Lokayukta Act 1984 empowers the Lokayukta to investigate complaints of maladministration by state government bodies including municipal corporations. Citizens can file a complaint with the Karnataka Lokayukta if the corporation fails to respond to civic grievances despite repeated requests. The RTI Act 2005 also applies to municipal corporations as they are public authorities under Section 2(h) of the RTI Act.',
    NULL,
    'https://dpal.kar.nic.in'
),
(
    '00000000-0000-0000-0000-000000000012'::uuid,
    'Karnataka Municipal Corporations Act — Water Supply and Sanitation Obligations',
    'The Karnataka Municipal Corporations Act 1976 places specific obligations on municipal corporations regarding water supply and sanitation. Section 108 requires the corporation to provide wholesome water supply to all areas within its limits. Section 122 requires the corporation to maintain drainage and sewerage systems in a clean and functional condition. The Mangaluru Water Works Department (MWWD) operates under the MCC and is responsible for water supply and sewage in Mangaluru. Citizens experiencing water supply failures or sewage overflows may file complaints directly with MWWD at 0824-2424444 or file an RTI application to the MCC PIO.',
    NULL,
    'https://dpal.kar.nic.in'
),

-- ---------------------------------------------------------------------------
-- Category 4: Sample RTI letter format
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000013'::uuid,
    'RTI Application — Sample Letter Format for Civic Complaint Follow-Up',
    'To, The Public Information Officer, [Authority Name], [Address], Mangaluru, Karnataka. Subject: RTI Application under Section 6 of the Right to Information Act 2005 — Civic Complaint Reference [Complaint Number]. I, [Applicant Name], a citizen of India, hereby request the following information under Section 6 of the Right to Information Act 2005 regarding my civic complaint. 1. Current status of the complaint bearing reference number [Complaint Number] submitted on [Date]. 2. Name and designation of the officer assigned to address the complaint. 3. Actions taken and timeline of inspections or repair work conducted. 4. Reasons for delay if the complaint remains unresolved after [Number] days.',
    NULL,
    NULL
),
(
    '00000000-0000-0000-0000-000000000014'::uuid,
    'RTI Application — Sample Letter Format (continued)',
    'The complaint was submitted on [Date] regarding [Issue Type] at [Location]. The complaint reference number is [Complaint Number]. Despite [Number] days having elapsed, the matter remains unresolved. I request the information within 30 days as prescribed under Section 7(1) of the RTI Act 2005. I am attaching proof of complaint submission as evidence. Application fee of Rs. 10 is enclosed/paid online (or) I am exempted as I am a Below Poverty Line cardholder (attach proof). Thanking you. Yours sincerely, [Applicant Name], [Address], [Phone], [Date]. Note: If no response is received within 30 days, a first appeal may be filed with the First Appellate Authority under Section 19(1) of the RTI Act 2005.',
    NULL,
    NULL
),

-- ---------------------------------------------------------------------------
-- Category 5: MCC contact hierarchy for escalation
-- ---------------------------------------------------------------------------
(
    '00000000-0000-0000-0000-000000000015'::uuid,
    'MCC and MESCOM Escalation Contact Hierarchy — Mangaluru',
    'Mangaluru City Corporation (MCC) Commissioner: 0824-2220055, commissioner@mangalurumahanagara.in. MCC North Zone office: 0824-2220066, northzone@mangalurumahanagara.in. MCC Drainage Division: 0824-2220077, drainage@mangalurumahanagara.in. Mangaluru Water Works Department (MWWD): 0824-2424444, waterworks@mangalurumahanagara.in. MESCOM (street lights and electricity): 1912, mangaluru@mescom.in. NHAI Mangaluru (national highways): 0824-2452001, mangaluru@nhai.org. Mangaluru Urban Development Authority (MUDA): 0824-2454321, commissioner@muda.gov.in. For RTI applications to MCC: address to the Public Information Officer, Mangaluru City Corporation, Lalbagh, Mangaluru — 575001.',
    NULL,
    'https://mangalurumahanagara.in'
),
(
    '00000000-0000-0000-0000-000000000016'::uuid,
    'RTI and Civic Complaint Escalation Hierarchy — When and How to Escalate',
    'Escalation timeline for unresolved civic complaints in Mangaluru. Day 1: Submit complaint to MCC/MWWD/MESCOM/NHAI as appropriate for the issue type. Day 30: If no resolution, submit first escalation to department head. Day 45: If still unresolved, file RTI application to MCC PIO under Section 6 of the RTI Act 2005, requesting complaint status and actions taken. Day 75 (30 days after RTI): If no RTI response, file first appeal to the First Appellate Authority at MCC under Section 19(1). Day 120 (45 days after first appeal): If first appeal unsatisfactory, file second appeal to Karnataka State Information Commission (KSIC) under Section 19(3). The KSIC can impose penalties and award compensation.',
    NULL,
    NULL
)

ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- match_rti_knowledge_base — PostgreSQL function for pgvector cosine search
-- Used by T2-12 vector_store.py search() via Supabase RPC
-- Architecture: Part B §Vector Search (T2-12)
-- =============================================================================
CREATE OR REPLACE FUNCTION public.match_rti_knowledge_base(
    query_embedding vector(1536),
    match_count      int DEFAULT 5
)
RETURNS TABLE (
    id         UUID,
    title      TEXT,
    content    TEXT,
    source_url TEXT,
    similarity FLOAT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        id,
        title,
        content,
        source_url,
        1 - (embedding <=> query_embedding) AS similarity
    FROM public.rti_knowledge_base
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

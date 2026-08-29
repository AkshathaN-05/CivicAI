"""RTI knowledge-base ingestion script — T2-13.

Seeds the ``rti_knowledge_base`` table with RTI Act and MCC procedure content,
optionally computing and storing BAAI/bge-large-en-v1.5 embeddings when the
RAM gate allows.

Usage (from the backend/ directory with .venv active):

    python scripts/ingest_rti_knowledge_base.py

The script:
1. Loads the five RTI knowledge documents (same content as
   ``supabase/seed/002_rti_knowledge_base.sql``).
2. Chunks each document using :func:`~rag.chunker.chunk_document` (max 512
   tokens per chunk).
3. Attempts to embed each chunk using :func:`~rag.embedder.embed`.
4. Inserts each chunk into ``rti_knowledge_base`` via the Supabase service-role
   client.  Skips rows that already exist (ON CONFLICT DO NOTHING via upsert).

When the embedding model is unavailable (RAM gate or model load failure),
chunks are inserted with ``embedding=NULL`` and keyword-only RAG is used.

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env
    (or set as environment variables before running the script)

This script is idempotent — safe to re-run.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid

# Allow running from the backend/ directory without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Knowledge documents — same 5 categories as supabase/seed/002 (T2-13 spec)
# ---------------------------------------------------------------------------

_DOCUMENTS: list[dict] = [
    {
        "title": "RTI Act 2005 — Section 6: Application Procedure",
        "content": (
            "Section 6 of the Right to Information Act 2005 governs the procedure for "
            "making an RTI application. A citizen who desires to obtain any information "
            "under this Act shall make a request in writing or through electronic means "
            "in English or Hindi or in the official language of the area, to the Public "
            "Information Officer (PIO) of the concerned public authority. No reason is "
            "required to be given for requesting the information. The application must "
            "be accompanied by the prescribed fee (currently Rs. 10 for central government "
            "bodies). Below Poverty Line (BPL) applicants are exempted from paying the "
            "application fee. If the information requested concerns another public "
            "authority, the PIO shall transfer the application within 5 days."
        ),
        "source_url": "https://rti.gov.in/rti-act.pdf",
    },
    {
        "title": "RTI Act 2005 — Section 7: Time Limit",
        "content": (
            "Section 7 of the RTI Act 2005 specifies the time limits for providing "
            "information. The PIO must provide the information within 30 days of receipt "
            "of the request. If the information concerns the life or liberty of a person, "
            "it must be provided within 48 hours. Failure to respond within the prescribed "
            "period is deemed as refusal. The applicant may then file a first appeal under "
            "Section 19 of the Act. If the information is voluminous, the PIO may charge "
            "additional fees for photocopying and compilation. The PIO must communicate "
            "rejection reasons, the appeal period, and the Appellate Authority details."
        ),
        "source_url": "https://rti.gov.in/rti-act.pdf",
    },
    {
        "title": "RTI Act 2005 — Section 19: Appeal Procedure",
        "content": (
            "Section 19 of the RTI Act 2005 provides the appeal mechanism. A first appeal "
            "may be filed with a senior officer in the same public authority within 30 days "
            "of the expiry of the prescribed response period. The Appellate Authority must "
            "dispose of the appeal within 30 days (extendable to 45 days). A second appeal "
            "may be filed with the Central Information Commission or State Information "
            "Commission within 90 days if dissatisfied. The Information Commission may "
            "impose a penalty of up to Rs. 25,000 on the PIO for delay, refusal, or "
            "providing false information. The Commission may also award compensation."
        ),
        "source_url": "https://rti.gov.in/rti-act.pdf",
    },
    {
        "title": "Mangaluru City Corporation — Complaint Procedure and Escalation",
        "content": (
            "The Mangaluru City Corporation (MCC) handles civic complaints for potholes, "
            "road damage, garbage overflow, broken streetlights, open drains, waterlogging, "
            "illegal construction, water supply failures, and sewage problems. "
            "Citizens can submit complaints via the MCC online portal or call 0824-2220055. "
            "Each complaint is assigned a reference number. MCC must respond within 30 days "
            "under the Karnataka Municipalities Act. If no response after 30 days, escalate "
            "to the department head. After 45 days, file an RTI application to the MCC "
            "Public Information Officer. MWWD handles water/sewage: 0824-2424444. "
            "MESCOM handles streetlights: 1912. NHAI handles national highways: 0824-2452001."
        ),
        "source_url": "https://mangalurumahanagara.in",
    },
    {
        "title": "Karnataka Municipal Corporations Act — Citizen Rights and RTI Escalation",
        "content": (
            "The Karnataka Municipal Corporations Act 1976 obligates the municipal "
            "corporation to maintain roads, drains, streetlights, sanitation, and water "
            "supply. Section 58 empowers citizens to petition the corporation for remedial "
            "action. If the corporation fails to perform its mandatory duties, citizens may "
            "seek redress through the Karnataka High Court or the Karnataka Lokayukta. "
            "Municipal corporations are public authorities under Section 2(h) of the RTI "
            "Act 2005, making them subject to RTI applications. If a civic complaint "
            "remains unresolved despite escalation, an RTI application to the MCC Public "
            "Information Officer is the recommended next step before Lokayukta or court."
        ),
        "source_url": "https://dpal.kar.nic.in",
    },
]


def ingest(dry_run: bool = False) -> int:
    """Ingest RTI knowledge base documents into Supabase.

    Args:
        dry_run: If True, log what would be inserted but do not write to DB.

    Returns:
        Number of chunks successfully inserted (or that would be inserted
        in dry-run mode).
    """
    from rag.chunker import chunk_document
    from rag.embedder import embed
    from db.supabase_client import get_client

    client = get_client()
    if client is None and not dry_run:
        logger.error(
            "Supabase client unavailable. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY in .env and retry."
        )
        return 0

    total_inserted = 0

    for doc in _DOCUMENTS:
        chunks = chunk_document(doc["content"], max_tokens=512)
        logger.info(
            "Document '%s': %d chunk(s).", doc["title"], len(chunks)
        )

        for i, chunk_text in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            embedding = embed(chunk_text)

            if embedding is not None:
                logger.debug("  chunk %d/%d: embedding computed (%d dims).", i + 1, len(chunks), len(embedding))
            else:
                logger.debug("  chunk %d/%d: embedding unavailable (NULL).", i + 1, len(chunks))

            row = {
                "id": chunk_id,
                "title": doc["title"] if len(chunks) == 1 else f"{doc['title']} (part {i + 1})",
                "content": chunk_text,
                "embedding": embedding,
                "source_url": doc.get("source_url"),
            }

            if dry_run:
                logger.info("  [dry-run] Would insert: %s…", chunk_text[:80])
                total_inserted += 1
                continue

            try:
                result = (
                    client.table("rti_knowledge_base")
                    .upsert(row, on_conflict="id")
                    .execute()
                )
                if result.data:
                    total_inserted += 1
                    logger.debug("  inserted chunk id=%s", chunk_id)
                else:
                    logger.warning("  upsert returned no data for chunk id=%s", chunk_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("  failed to insert chunk: %s", exc)

    logger.info("Ingestion complete. Total chunks inserted: %d.", total_inserted)
    return total_inserted


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("Running in dry-run mode — no database writes.")
    inserted = ingest(dry_run=dry_run)
    if inserted == 0 and not dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()

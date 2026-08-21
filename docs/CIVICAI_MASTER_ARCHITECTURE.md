# CivicAI — Master Architecture Document
**Version:** 2.0 (Final Approved)
**Status:** LOCKED — Do not modify without an ADR
**Jurisdiction:** Mangaluru, Karnataka, India
**Budget:** ₹0 / $0

---

## Table of Contents

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

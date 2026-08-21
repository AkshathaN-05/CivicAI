# CivicAI

[![CI](https://github.com/YOUR_ORG/civicai/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/civicai/actions/workflows/ci.yml)

A zero-cost Progressive Web Application for civic issue reporting in Mangaluru, Karnataka, India.

## Overview

Citizens photograph civic problems using their device camera. An AI pipeline classifies the issue, estimates evidence confidence, detects duplicates, redacts privacy-sensitive content, and recommends the correct Mangaluru authority. The citizen reviews every AI recommendation, corrects if needed, and approves before submission.

After 30 days of no government progress, an RTI (Right to Information) flow becomes available — AI drafts the RTI, citizen reviews and approves, and a mock submission is made.

**Core principles:**
- Zero cost — every service used is genuinely free at hackathon scale
- Camera-first — fresh photo capture only, no gallery upload in main flow
- AI assists, citizen decides — no automated submission ever
- Authority data is immutable — Mangaluru authority JSON is the source of truth
- Security is primary — not an afterthought
- Privacy by design — faces and plates are redacted before any public storage
- Offline-first PWA — complaints survive connectivity loss with clear state labels

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python 3.11 |
| Database | Supabase (PostgreSQL 15 + PostGIS + pgvector) |
| AI/CV | YOLOv8n, YuNet ONNX, fast-alpr, BAAI/bge-large-en-v1.5 |
| LLM | Groq API (llama-3.1-8b-instant) + deterministic fallback |
| Maps | MapLibre GL JS + OpenFreeMap tiles |
| PWA | next-pwa (serwist) + idb-keyval |
| Hosting | Vercel (frontend) + Render (backend) |

**Total cost: ₹0 / $0**

## Repository Structure

```
civicai/
  frontend/          Next.js 14 App Router frontend
  backend/           FastAPI Python backend
  supabase/          Database migrations and seed data
  .github/           CI/CD workflows
  docs/              Architecture and implementation plan
```

## Documentation

The complete architecture and implementation plan is in:

- [`docs/CIVICAI_MASTER_ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md`](docs/CIVICAI_MASTER_ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md)

The LOCKED master architecture is in:

- [`docs/CIVICAI_MASTER_ARCHITECTURE.md`](docs/CIVICAI_MASTER_ARCHITECTURE.md)

## Development Setup

> **Status:** Repository scaffolding complete (T0-1). See the implementation plan for next steps.

Individual setup instructions for frontend and backend will be added as each phase is completed.

## Jurisdiction

Mangaluru, Karnataka, India

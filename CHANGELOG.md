# Changelog

## [Unreleased]
### Added
- `intelligence_core`: layer condiviso (chunk, embedder, retriever, escalation, store, server_base)
- `CodeIntelligence`: parser multi-linguaggio (Python AST, TS, Go, YAML, SQL, MD)
- `DocIntelligence`: parser documenti (PDF, DOCX, XLSX, MD, TXT)
- `MentorIntelligence`: orchestratore onboarding adattivo (profile, session, path, orchestrator)
- Formato chunk unificato `domain::type::locator` con `domain=mentor`
- Policy escalation configurabile locale → Claude API
- Test suite: Hit@K, MRR, NDCG, KPI thresholds, Parser PDF/DOCX, Mentor
- 16 query di benchmark con chunk target
- Documenti di esempio reali (PDF, DOCX, XLSX)

## [0.1.0] — 2026-05-25
- Primo commit. Struttura e skeleton completo.

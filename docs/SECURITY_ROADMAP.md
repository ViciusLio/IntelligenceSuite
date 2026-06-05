# Security & Data-Segregation Roadmap

> **Status:** Planning / not yet implemented.
> **Scope:** Authentication (SSO), authorization (segregation), data-layer hardening, and EU-regulation alignment for on-premise, per-client deployments of IntelligenceSuite.
> **Guiding constraints:** zero breaking changes (every new feature is opt-in and defaults to current behaviour); single enforcement point; defense-in-depth.

---

## 1. Decisions (locked)

| Decision | Choice | Consequence |
|----------|--------|-------------|
| Deployment model | **On-prem, one deployment per client** | Multi-tenancy is secondary; the real perimeter is *intra-deployment* (group/role/classification). `IS_PROJECT` stays only for project separation inside a client. |
| Authorization granularity | **Group + Role + Classification** (3-axis ABAC) | Access = intersection of the three axes, evaluated at query time. |
| SSO provider | **Microsoft Entra ID** (OIDC) | JWT validated against Entra JWKS; claims → `Principal`. |
| ACL source | **External configurable policy file** | `acl_policy.yaml`, admin-managed, decoupled from content. |
| DB defense-in-depth | **pgvector + Postgres RLS, from the start** | Segregation lives in the DB, not only in the app. `allowed_groups` lists need Postgres arrays (ChromaDB cannot store list metadata). |
| First secure deliverable | **AuthN + AuthZ together** | First release is genuinely secure, not a login demo. |

---

## 2. Authorization model — 3-axis ABAC

Every indexed chunk carries ACL metadata; every authenticated user carries attributes derived from Entra. Access is the intersection of all three axes.

| Axis | On the **chunk** | On the **user** (from Entra JWT) |
|------|------------------|----------------------------------|
| Classification | `classification: public \| internal \| confidential \| restricted` | `clearance` (max readable level) |
| Group | `allowed_groups: [<entra-group-oid>, ...]` | `groups: [<oid>, ...]` |
| Role | `min_role: viewer \| editor \| admin` (optional) | `roles: [...]` (Entra App Roles) |

**Access rule (evaluated at query time):**

```
visible(chunk, user) =
    user.clearance >= chunk.classification
    AND (chunk.allowed_groups is empty OR intersect(user.groups, chunk.allowed_groups) != empty)
    AND user.role >= chunk.min_role
```

The existing `store.search(filters=...)` already forwards a `where` filter to the backend. Enforcement = translate this rule into the backend filter and inject it at a **single** point.

---

## 3. ACL policy — external configurable file (Phase 0)

Admin-managed, separated from the documents themselves.

```yaml
# acl_policy.yaml  (managed by the client admin, not by content authors)
rules:
  - match: "**/finance/**"
    classification: confidential
    allowed_groups: ["finance"]        # human-readable, mapped to Entra OID via group_map
  - match: "**/hr/**"
    classification: restricted
    allowed_groups: ["hr"]
  - match: "docs/public/**"
    classification: public
default:
  classification: internal

# group_map: human name -> Entra group object-ID (GUID)
group_map:
  finance: "a1b2c3d4-....-finance-oid"
  hr:      "c3d4e5f6-....-hr-oid"
```

- At **ingest**, each chunk's path is resolved against these rules → writes `classification` + `allowed_groups` (resolved to OIDs) into the chunk metadata.
- Changing a rule → targeted re-ingest; content is never touched.
- `group_map` lets the admin write readable names instead of GUIDs.

---

## 4. Data layer — pgvector + Postgres RLS (Phase 1)

- Complete `PgVectorStore` (today a skeleton raising `NotImplementedError`).
- Each embedding row carries `classification`, `allowed_groups` (Postgres array), `project`.
- **Row-Level Security policy** compares row columns against session variables set per-connection from the `Principal`:
  - `SET app.user_clearance = ...`
  - `SET app.user_groups = ...`
- Effect: even if an application bug forgets the `where` filter, **Postgres returns no rows above clearance**. This is the defense-in-depth layer.
- `VECTOR_STORE=pgvector` toggle; ChromaDB stays the default for deployments that don't need RLS → zero breaking change.

> **Why not ChromaDB for ACL:** ChromaDB metadata accepts only scalars (str/int/float/bool), **not lists**. `allowed_groups` as a list is not natively storable/queryable. pgvector arrays + `&&` (overlap) operator are required for group-based segregation.

---

## 5. Authentication + Authorization — Entra ID (Phase 2)

**Flows:** OIDC Authorization Code + PKCE for interactive UI; Client Credentials for service-to-service (batch ingest).

1. **App registration** in the client's Entra tenant → `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, issuer/JWKS URI.
2. **Token validation** middleware (extends/sits beside `BearerAuthMiddleware`):
   - verify JWT signature against Entra JWKS,
   - check `aud`, `iss`, `exp`,
   - extract claims → build `Principal(user_id, groups[], roles[], clearance)`.
3. **Entra → suite mapping:**
   - **Groups:** the `groups` claim contains group **object-IDs** (GUIDs). `group_map` translates readable names → OIDs.
   - **Roles:** use Entra **App Roles** (cleaner than groups) → `roles` claim.
   - **Groups overage:** if a user is in >200 groups Entra omits them from the token and sends a Graph reference → fallback to Microsoft Graph `getMemberObjects`.
4. **Same cycle**, the `Principal` drives the security filter injection (below) and, with pgvector, sets the Postgres session variables for RLS.

**Auth mode toggle (opt-in, backwards compatible):**
`IS_AUTH_MODE=none` (default, current behaviour) | `bearer` (current single token) | `entra` (OIDC).

---

## 6. Single enforcement point

The security `where`-filter is injected in **one** place — `Retriever.search` — so every consumer inherits it:

- normal RAG query ✓
- **agent tools** (when `INTENT_AGENT_ENABLED=true`) ✓ — otherwise the agent bypasses ACL
- **escalation to Claude** ✓ — context sent externally must already be filtered (see §7)
- **export** ✓
- **graph retriever** ✓

If `Principal` is absent (auth disabled) → empty filter → behaviour identical to today.

Auth middleware itself lives in `server_base.create_app` (shared by all module servers) — **never** duplicated per server. A test asserts every module port returns 401/403 without a valid token.

---

## 7. CRITICAL — no-egress for restricted data

Today, low-confidence queries escalate to Claude (`api.anthropic.com`, outside the on-prem perimeter and **outside the EU**). Retrieved context may be `confidential`. This nullifies segregation and is the primary GDPR transfer risk.

**Mandatory rule (highest priority, small change):**
- The security filter runs **before** escalation.
- Chunks with `classification >= confidential` **never** leave to an external provider.
- Either: escalation disabled for those levels, or escalation only to an on-prem LLM.

This is item **0.5** in the action plan — implemented before the rest because it is small and high-impact.

---

## 8. Audit (Phase 3)

- Extend existing observability: add `principal_id` to every query and escalation log line.
- Provides the access traceability required by GDPR and the AI Act.
- Question/answer text is still **never** logged — only metadata + principal.

---

## 9. Known infrastructure criticalities & mitigations

| # | Criticality | Mitigation |
|---|-------------|-----------|
| 1 | 🔴 Escalation to Claude exfiltrates `confidential` data outside EU | No-egress gate (§7), implemented first |
| 2 | 🟠 ChromaDB cannot store list metadata (`allowed_groups`) | Group ACL requires pgvector (Postgres arrays) |
| 3 | 🟠 6 separate FastAPI servers → auth must be uniform | Enforce in shared `create_app` + `Retriever.search`; per-port 401 test |
| 4 | 🟡 Secrets in plaintext `.env` (e.g. Anthropic key) | Secrets store / orchestrator-injected env before production; rotate exposed key |
| 5 | 🟡 Embedding dimension lock-in; no delete-by-document | Build re-index + deletion paths (also required for GDPR erasure) |
| 6 | 🟡 Silent config traps (pydantic vs os.getenv) | End-to-end test for every security toggle; never trust defaults |

---

## 10. EU regulation alignment

> ⚠️ Technical framing only — validate with a DPO / legal counsel before production at a client.

**GDPR** (documents likely contain personal data):
- **Cross-border transfer:** escalation to Claude (USA) is an international transfer → SCCs required, or disabled for personal/confidential data (§7).
- **Right to erasure / rectification:** must be able to delete embeddings derived from a document → deletion path to build (criticality #5).
- **Data minimization + access control:** the segregation here *is* need-to-know — directly satisfies this.
- **Access logging:** the audit phase (§8) covers traceability.

**EU AI Act** (in force Aug 2024, phased to 2026/27):
- **Risk depends on USE, not on the software.** The suite is a retrieval tool (minimal/limited risk). If the *client* uses it for HR, credit scoring, justice, etc. → high-risk use → conformity obligations (risk management, data quality, logging, human oversight, technical documentation).
- **Transparency:** users must know they interact with an AI → UI disclosure/banner.
- **GPAI flow-down:** third-party models (Qwen, Claude) → traceability of model + version.
- **Traceability/logging:** covered by the audit phase.

**Bottom line:** the architecture *enables* compliance (access control, audit, segregation), but final conformity depends on how the client uses it and on organizational policies (DPIA, processing register, disclosure) that live outside the code. The piece the code **must** guarantee and that is currently uncovered is the **no-egress of restricted data** (§7).

---

## 11. Phased roadmap

| Phase | Deliverable | Releasable on its own |
|-------|-------------|-----------------------|
| **0** | `acl_policy.yaml` + `group_map` + metadata enrichment at ingest | Yes |
| **0.5** | 🔴 No-egress gate on escalation (highest priority) | Yes |
| **1** | `PgVectorStore` complete + ACL columns + RLS policy | Yes |
| **2** | Entra OIDC middleware (`Principal`) + security filter at `Retriever.search` (all paths) | Yes |
| **3** | `SET app.*` session vars to activate RLS from `Principal`; audit `principal_id` | Yes |
| **4** | (Optional) Neo4j Enterprise if the graph must be segregated; secrets store | On demand |

**Recommended order:** 0 → **0.5** → 1 → 2 → 3. Stop and measure after Phase 2/3 before investing in Phase 4.

---

## 12. Non-goals (for now)

- Multi-tenant isolation against hostile co-tenants (single-client on-prem makes this secondary).
- Neo4j Enterprise (only if a client requires graph segregation at scale).
- Replacing ChromaDB as the default (pgvector is opt-in via `VECTOR_STORE`).

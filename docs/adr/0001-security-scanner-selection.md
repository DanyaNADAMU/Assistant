# ADR-0001: Security Scanner Selection — One Gate per Supply-Chain Layer

* **Status**: Accepted
* **Date**: 2026-11-24
* **Authors**: agent
* **Deciders**: Danyanadamu

---

## 1. Context and Problem Statement

The Assistant pipeline shipped with a single security gate (the Trivy image
scan in the shared catalog). The adjacent layers of the supply chain —
source code, Python dependencies, secrets in git history, and build
provenance — had no scanner at all. This ADR records which tools were chosen
to close each layer, which were rejected, and under what conditions a chosen
tool would be replaced.

## 2. Decision Drivers

* Every repository in the organization is public by design: GitHub-native
  security features (CodeQL, secret scanning, push protection, Dependabot
  alerts) are permanently free — exploit them before any paid or third-party
  tool.
* The shared `Danyanadamu/Workflows` catalog holds zero secrets: every added
  scanner must run without new credentials, or receive them from the caller.
* Minimal new trust roots: every third-party action is another link to pin
  and audit; prefer first-party actions or pinned binaries fetched from
  official release channels.
* One gate per layer: overlapping scanners multiply maintenance, pins, and
  false-positive surface without adding coverage.
* Deterministic CI blocking beats passive alerting: gates live in the
  repository, signed and versioned; policy changes are reviewable commits.

## 3. Considered Options

* **Option 1 — GitHub-native only** (CodeQL + secret scanning + Dependabot
  alerts, no CI gates): zero maintenance, but no SCA gate inside the test
  suite and no history-wide secret scan for the custom secret formats GitHub
  does not know.
* **Option 2 — third-party suite** (Snyk, Safety, SonarQube): all rejected —
  accounts, SaaS dependencies, or paid databases violate the zero-secrets
  catalog and "GitHub is the sole origin" principles.
* **Option 3 — one pinned, local tool per layer** (chosen set below):
  Trivy (image, existing), CodeQL (SAST), `uv audit` (SCA), gitleaks
  (secret history scan), Sigstore provenance via
  `actions/attest-build-provenance` + `gh attestation verify` (supply chain).

## 4. Decision Outcome

Chosen option: **Option 3**, because each layer gets exactly one
best-fit gate, every gate runs free and local, and the set composes with
the existing pipeline instead of replacing it.

| Layer | Tool | Why this one | Rejected alternatives |
|---|---|---|---|
| Image CVEs | Trivy 0.76.2 (catalog) | already integrated; single binary; gate = CRITICAL + `--ignore-unfixed`, full report parked as an artifact | Grype (lateral swap, no new layer); Snyk (account) |
| SAST (Python) | CodeQL via catalog `sast.yml` | free on public repos, first-party, taint-flow beyond AST lint | bandit (AST heuristics, high FP); semgrep (curated rulesets to maintain) |
| SCA (deps) | `uv audit --locked` | native to the existing uv toolchain; audits the exact lockfile; PyPA advisory DB | pip-audit (cannot read `uv.lock` natively); Safety (paid DB) |
| Secret history | gitleaks 8.30.1 | pure detection (no live-credential calls from CI), custom-rule allowlist for local formats | TruffleHog (live verification = side-effect calls from CI) |
| Build provenance | `attest-build-provenance` + `gh attestation verify` | first-party, keyless (runner OIDC), verified on the deploy path; the buildx in-index provenance turned out to be unsigned and unverifiable | cosign (needs signed attestations that nothing produced) |
| Continuous CVE signal | Dependabot alerts + scheduled image re-scan | alerts cover dependencies between pushes; `scan-cron.yml` covers the deployed image post-release | none — complementary, not overlapping |

### Positive Consequences

* Five layers, five gates, zero new accounts, zero new third-party actions
  (all new actions are first-party or pinned binaries).
* Every gate either rides an existing pipeline (uv audit inside the test
  action, Trivy inside the catalog build) or is a small explicit job.

### Negative Consequences / Tradeoffs

* `attestations`/`id-token` grants must live on caller jobs (GitHub rejects
  them in reusable workflows' own blocks) — a documented wiring contract.
* Trivy/binary pins are updated by Renovate regex managers, not by hand;
  until `RENOVATE_TOKEN` is provisioned those pins are manual.

## 5. Pros and Cons of the Options

### Option 1 — GitHub-native only
* Good, because zero maintenance.
* Bad, because no in-suite SCA gate and no history scan for custom secret
  formats.

### Option 2 — third-party suite
* Good, because polished dashboards.
* Bad, because accounts/SaaS/paid DBs violate the catalog's zero-secret and
  single-origin principles.

### Option 3 — one pinned local gate per layer
* Good, because free, auditable, fail-closed, and composable.
* Bad, because pin maintenance (accepted: Renovate owns it).

## 6. Links and References

* The 2026-03 Trivy supply-chain incident (malicious v0.69.4 release and
  compromised `trivy-action` for ~12 hours) is the empirical anchor for the
  pinned-binary pattern: the catalog pins the exact version and fetches from
  official release channels, so a floating tag or an auto-pulled "latest"
  would have walked into it.
* Catalog: `Danyanadamu/Workflows` PR #4 (provenance verification,
  `sast.yml`, `scan-cron.yml`, `protection-audit.yml`).
* Replacement triggers, honored over time: Trivy→Grype if registry-integrated
  continuous scanning becomes required; CodeQL→semgrep if this repository
  goes private (GHAS cost) or non-Python surfaces appear; uv audit→
  osv-scanner if multi-ecosystem lockfiles appear; gitleaks→TruffleHog if
  live-credential verification becomes a wanted manual ritual.

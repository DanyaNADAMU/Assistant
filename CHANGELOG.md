# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`uv audit` in the test suite**: native SCA over the exact `uv.lock`
  the image installs (PyPA advisory database) — a known-vulnerable pin
  fails the suite before any image is built from it.
- **gitleaks full-history secret scan** on every push: push protection
  guards only the future, and the append-only timeline means anything
  leaked before it can only be discovered, never silently removed.
  Allowlist tuned for lockfiles and OTS proofs (`.gitleaks.toml`).
- **CodeQL SAST** via the shared catalog (`sast.yml`, python) on pushes,
  PRs, and weekly — free on public repositories, first-party, taint-flow
  beyond AST lint reach. Selection rationale recorded in
  `docs/adr/0001-security-scanner-selection.md`.
- **Deploy provenance verification**: the release build's digest is
  Sigstore-signed (`actions/attest-build-provenance`, runner OIDC) and
  `deploy.yml` verifies it before anything touches a host — a
  substituted or unattested image fails closed.
- **Scheduled re-scan of the deployed image** (`scan-cron.yml`): a CVE
  published after a release becomes a red run and a patch-release
  signal instead of sitting silently in production.
- **Protection drift audit** (`protection-audit.yml` + committed
  `.github/protection-expected.json`): the live main-branch protection
  and release-tag ruleset are diffed against the committed contract on a
  schedule; needs the read-only `PROTECTION_AUDIT_TOKEN`, warns until
  provisioned.
- **Self-hosted Renovate** (`renovate.json` + `renovate-cron.yml`):
  dependency update PRs for action pins and curl-pinned scanner
  binaries, validated by the same pipelines they feed; needs
  `RENOVATE_TOKEN`, warns until provisioned.
- **GitHub Releases on tags**: the CHANGELOG section of a tag is
  published as a Release object right after the Ice rollout it
  describes.

### Changed
- **Main is a protected linear branch on GitHub**: enforce-admins, no
  force pushes, no deletions — the "never force-push to main" invariant
  now has a technical holder, not just the rules. Merges are
  rebase/squash from here on.
- **Release tags are ruleset-protected** (`refs/tags/v*`: no deletion,
  non-fast-forward only).
- **Same-branch pushes no longer cancel running deploys**
  (`cancel-in-progress: false`): the wrapper owns capture/rollback
  atomically and a half-cut deploy is what it exists to prevent.
- Documentation-only pushes (`docs/**`, `**.md`) no longer trigger the
  image build and the staging roll.

### Fixed
- **Daily OpenTimestamps cron unblocked** (catalog `ots.yml` fix): a
  lost calendar submission (the v1-era squash commit 977619d, pending
  since Nov 22) red-locked the loop — the pending proof could never
  reach `main`, so no later cron could upgrade it. Young pending proofs
  now ride the push with a warning and get upgraded by later runs; only
  a proof pending for a week or more is red, with a re-stamp signal.

### Added
- Reusable test suite composite action (`.github/actions/test`) shared by
  the build and release pipelines: ruff lint/format, mypy strict, pytest,
  with a uv cache keyed on `uv.lock`.

### Changed
- Build both trunk and release images through the shared
  `Workflows/container-build.yml` catalog: lowercase GHCR name
  normalization, GHA layer cache, provenance + SBOM attestations, and a
  CRITICAL-gated Trivy scan on pushed refs.
- Release pipeline now runs the release precheck gate (strict SemVer,
  CHANGELOG section, SSH tag-signature verification, ancestry from
  `main`) and the full test suite before the release image is built;
  previously a tag could ship without tests ever running.
- Cancel superseded same-branch pipeline runs via concurrency groups;
  runners pinned to `ubuntu-24.04`; all actions pinned to commit SHAs.
- Grant `contents: write` explicitly to the `ots` cron job (the right
  `ots.yml` needs to push upgraded proofs back to `main`).

## [v0.3.0] - 2026-11-19

### Changed
- Rebrand the project from **SummaryBot** to **Assistant**: Python package `summary_bot` → `assistant`, CLI entrypoint `summary-bot` → `assistant`, and every user-facing name, container, and document.
- Move container image publishing to GitHub Container Registry (`ghcr.io/danyanadamu/assistant`).

### Added
- GitHub Actions CI/CD: test/lint/typecheck job (`pytest` + `ruff` + `mypy strict`), image build, and digest-pinned forced-command deploys.
- Staging deployment to the **Actions** test sandbox (feature/fix branches) and production deployment to **Ice** (signed tags).

### Removed
- Forgejo CI and the legacy `git.nada.mu` Kaniko registry pipeline.

## [v1.0.0] - 2026-11-09

### Added
- Standard project baseline with OpenTimestamps cryptographic anchoring.
- Dual-language living documentation structure.
- Automated Bitcoin timestamping workflow.
- Standard versioned Git hooks and release gate toolchain.

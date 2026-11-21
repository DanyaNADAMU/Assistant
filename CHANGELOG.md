# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

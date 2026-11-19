# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

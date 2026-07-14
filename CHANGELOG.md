# Changelog

All notable changes to this project are documented here. The format is based on Keep a Changelog, and the project uses semantic versioning before 1.0 as a compatibility signal rather than a stability guarantee.

## [Unreleased]

### Added

- Repository hygiene tests, macOS CI, Dependabot and community-health documentation.

## [0.2.0] - 2026-07-13

### Added

- Application/window-targeted MCP actions with strict Accessibility semantics.
- Per-session persistent workers, target locks, snapshots and cursor feedback.
- Official-inspired but independently drawn aqua-arrow cursor overlay.
- Covered-target, concurrent-worker, native-application and focus-lifecycle verification.

### Changed

- Mouse-like actions no longer use desktop-global delivery or move the physical pointer.
- Application launch and overlay setup use nonactivating lifecycle policies.

### Security

- Unsupported background actions fail before delivery.
- Secure Accessibility values are redacted and target state is revalidated before actions.

[Unreleased]: https://github.com/Zss03040464/computer-use-fallback-mac/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Zss03040464/computer-use-fallback-mac/releases/tag/v0.2.0

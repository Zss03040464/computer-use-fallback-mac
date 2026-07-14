# Changelog

All notable changes to this project are documented here. The format follows Keep a Changelog, and versions before 1.0 use semantic versioning as a compatibility signal rather than a stability guarantee.

## [Unreleased]

### Added

- Repository hygiene tests, macOS CI, Dependabot and community-health documentation.
- Allowlisted compatibility worker for display capture, permissions, clipboard, coordinate mapping and read-only OCR.
- Privacy verification and an exact, hash-verified Python dependency lock.

### Changed

- Worker calls now use bounded persistent JSON Lines protocols with structured errors and shutdown.
- The public repository surface now contains stable product, architecture and verification documentation only.
- Pillow is locked to 12.3.0 and the documented minimum Python version is 3.10.

## [0.2.0] - 2026-07-14

### Added

- Application/window-targeted MCP actions with strict Accessibility semantics.
- Per-session persistent workers, target locks, snapshots and cursor feedback.
- Independently designed `aqua-glass-arrow-v2` virtual-cursor overlay.
- Covered-target, concurrent-worker, native-application and focus-lifecycle verification.

### Changed

- Mouse-like actions do not use desktop-global delivery or move the physical pointer.
- Application launch and overlay setup use nonactivating lifecycle policies.

### Security

- Unsupported background actions fail before delivery.
- Secure Accessibility values are redacted and target state is revalidated before actions.

[Unreleased]: https://github.com/Zss03040464/computer-use-fallback-mac/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Zss03040464/computer-use-fallback-mac/releases/tag/v0.2.0

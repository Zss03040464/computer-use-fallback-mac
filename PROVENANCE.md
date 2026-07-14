# Source Ownership

All project-specific production source code, tests, documentation and virtual-cursor artwork in this repository are independently designed, implemented and maintained by this repository's contributors.

## Repository implementation

The project-specific implementation includes:

- the Node.js MCP server, tool schemas, handlers and bounded worker clients;
- the Python application/window-targeted runtime and allowlisted compatibility runtime;
- target discovery, ScreenCaptureKit capture, Accessibility snapshots and semantic actions;
- session isolation, target locks, virtual-cursor state, rendering and overlay lifecycle;
- deterministic, integration, native macOS, packaging, privacy and repository-hygiene tests.

## Platform APIs and dependencies

The runtime integrates public macOS APIs through PyObjC, including Accessibility, AppKit, CoreGraphics, ScreenCaptureKit and Vision.

External packages are declared in `package-lock.json` and `runtime/requirements.txt`. They remain subject to their respective licenses and copyright notices. The repository's MIT license applies to the project-specific implementation and does not replace dependency licenses.

## Verification

The release gates verify:

- absence of desktop-global and unverified process-targeted input delivery;
- physical-pointer, foreground-application, target and session isolation;
- no sensitive request/response persistence;
- exact and hash-verified dependency installation;
- tracked-file hygiene, valid documentation links and clean packaging;
- deterministic, controlled integration and real-macOS behavior.

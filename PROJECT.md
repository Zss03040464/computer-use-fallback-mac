# Project

## Goal

`computer-use-fallback-mac` is an independently designed macOS MCP component for application/window-targeted Computer Use. Supported background actions must reach the explicit target without moving the physical pointer, changing the frontmost application or falling through to the visible desktop.

## Current status

Version `0.2.0` provides persistent per-MCP Python workers, target-window capture, Accessibility window snapshots, strict semantic actions, stale-element validation, cross-process target locks and session-scoped overlays.

Display capture, permission inspection, plain-text clipboard access, coordinate mapping and read-only OCR run in a separate allowlisted compatibility worker. It has no input-delivery, application-activation, window-raising or overlay capability.

The repository-owned `aqua-glass-arrow-v2` cursor uses a 13 by 18 logical-pixel translucent cool-white arrow, soft bloom and a weak aqua clipped-tail edge. The live AppKit overlay and target-window PNG compositor consume the same geometry, palette and pulse timing.

Live verification monitors HID activity and workspace activation before any target, blocker or overlay setup. Exact pointer equality is required when no hardware movement occurs; protected targets and overlays may never become frontmost, even temporarily.

Built-in global and unverified PID event delivery is disabled. A target without a verifiable Accessibility action returns a structured error before delivery.

## Entry points

- Runtime and MCP map: `SOURCE_MAP.md`
- Installation: `MCP_INSTALL.md`
- Calling workflow and error recovery: `docs/COMPUTER_USE_OPERATION_GUIDE.md`
- Runtime architecture: `knowledge/architecture/app-targeted-runtime.md`
- Compatibility architecture: `knowledge/architecture/compatibility-runtime.md`
- Current delivery state: `TASKS.md`
- Project knowledge: `knowledge/HOME.md`

# Project

## Goal

`computer-use-fallback-mac` is a standalone macOS MCP component for application/window-targeted Computer Use. Supported background actions must reach the explicit target without moving the physical pointer, changing the frontmost application, or falling through to the visible desktop.

## Current status

Version `0.2.0` implements a persistent per-MCP Python worker, target-window capture, AX window snapshots, strict AX-first actions, stale element validation, per-target locks and session-scoped overlays. Verified mouse-like actions now write one target-bound cursor record used by both the live overlay and the next `get_app_state` PNG, matching the official state-action-state feedback lifecycle.

Cursor artwork now uses the shared original `fallback-official-aqua-arrow-v2` contract: a 13 by 18 logical-pixel translucent cool-white arrow, soft non-ring bloom, rounded antialiasing, and a weak aqua clipped-tail edge as the distinguishing detail. The AppKit overlay is a nonactivating panel under a prohibited activation policy, so its Python process cannot replace the user's foreground application.

Live verification now starts a read-only HID and workspace-activation monitor before any target, blocker or overlay setup. Exact pointer equality remains required when no hardware movement occurs. Every activation transition is retained: protected PIDs may never appear, temporary activate-and-restore is a failure, and ordinary typing cannot excuse a transition. Only a physical mouse-down or Command-Tab may attribute an unrelated application switch.

Production `get_app_state` retains `NSWorkspaceLaunchWithoutActivation | NSWorkspaceLaunchAsync`. Official Computer Use and this runtime were both observed launching System Settings while Codex remained frontmost throughout the launch interval. Test fixtures no longer raise, focus, activate or restore applications.

The GitHub publication surface is a curated private snapshot. Automated repository-hygiene tests exclude local agent/session/history state, runtime artifacts, credentials and personal absolute paths while preserving verified product knowledge, source, tests and provenance.

Built-in raw global and PID event delivery is disabled. A target without a verifiable AX action returns a structured error before delivery.

## Entry points

- Runtime and MCP map: `SOURCE_MAP.md`
- Install and external-agent setup: `MCP_INSTALL.md`
- Calling workflow and error recovery: `docs/COMPUTER_USE_OPERATION_GUIDE.md`
- Verified architecture: `knowledge/architecture/app-targeted-runtime.md`
- Current delivery evidence: `TASKS.md`
- Project knowledge: `knowledge/HOME.md`

# Compatibility runtime

## Goal

Provide a minimal macOS service for display capture, permission inspection, clipboard access, coordinate mapping and read-only CAPTCHA detection while keeping all input delivery inside the application/window-targeted runtime.

## Architecture boundary

```text
MCP stdio
  -> tool handlers
     -> app-targeted RuntimeWorker -> runtime/worker.py -> runtime/cu_runtime/
     -> CompatWorker              -> runtime/compat_worker.py -> runtime/compat_services/
```

`runtime/compat_services/` owns only:

- Accessibility and Screen Recording permission inspection;
- full-display and bounded display-region capture;
- plain-text clipboard read/write;
- logical/physical display coordinate conversion;
- read-only OCR keyword detection on a captured display image.

It cannot deliver input, activate applications, raise windows, click popups or own cursor overlays.

## Protocol

The compatibility worker uses the same bounded JSON Lines request/response shape as the app-targeted worker:

```json
{"id":"request-id","command":"check_permissions","payload":{}}
```

Responses contain either a result or a structured error with a stable code. Only an explicit command allowlist is dispatched; unknown commands fail without evaluating arbitrary functions.

## Public API integrations

- ScreenCaptureKit and CoreGraphics for display discovery and capture;
- Accessibility APIs for permission inspection only;
- AppKit `NSPasteboard` for plain-text clipboard access;
- Vision for read-only OCR;
- Pillow for deterministic image encoding and bounded resizing.

## Privacy contract

- No request/response file logger is created.
- Clipboard text, OCR text, user input, screenshots and Base64 are never emitted to stderr.
- Errors expose minimal diagnostics without sensitive payload values.
- OCR returns only a boolean and matched normalized keywords, never the complete recognized text.

## Capture and coordinate contract

- `displayId` selects one active display or defaults to the main display.
- Results report logical dimensions, pixel dimensions, backing scale and display identifier.
- Region requests use logical display-local coordinates and reject empty or out-of-bounds rectangles.
- Single-dimension resizing preserves aspect ratio.
- Logical/physical conversions retain display origins and independent X/Y backing scales.

Verification is anchored by `tests/python/test_compat_service.py`, `tests/node/compat-worker.test.mjs`, `tests/live/compat-services.test.mjs` and the clean-copy installation smoke.


# Tasks

## Version 0.2.0 release

Status: complete and verified.

Delivered capabilities:

- explicit application/window targeting;
- target-window capture and Accessibility snapshots;
- verified click, text, key, scroll and drag semantics;
- per-session state, target locks and concurrent-window isolation;
- click-through virtual cursor overlay and screenshot feedback;
- allowlisted capture, permission, clipboard, coordinate and read-only OCR services;
- exact, hash-locked Python dependency installation;
- repository hygiene, security, packaging and hosted CI gates.

Verification baseline:

- Python and Node unit suites;
- covered-window and concurrent-target integrations;
- Calculator, TextEdit, Safari and optional existing-Edge native checks;
- complete focus lifecycle and physical-pointer isolation;
- clean-copy installation and MCP stdio handshake;
- dependency, syntax, source-purity, Markdown-link and Git gates.

## Maintenance boundary

- Unsupported background actions must fail before delivery.
- Production paths must not activate applications, raise target windows or post desktop-global mouse events.
- Published files must contain no local session state, credentials, personal paths or internal process records.
- Real macOS UI checks remain explicit and serial.

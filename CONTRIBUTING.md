# Contributing

Thank you for improving `computer-use-fallback-mac`.

## Development requirements

- macOS 13 or later for native integration and live verification;
- Node.js 20 or later;
- system Python 3 with `venv` support;
- Accessibility and Screen Recording permissions only for explicit live tests.

## Setup

```bash
npm ci
node tests/packaging/bootstrap-client.mjs
npm test
```

`npm test` is the deterministic CI gate. `npm run test:live` creates controlled native fixtures and must be run serially on a suitable Mac. It must not be added to hosted CI as a substitute for real permission and physical-pointer verification.

## Change requirements

1. Keep actions bound to an explicit application PID and CoreGraphics window.
2. Never add desktop-global input, application activation, `AXRaise`, silent fallback delivery or physical-pointer movement.
3. Add a failing regression test before changing production behavior.
4. Run `npm test`, `npm run test:clean-install` and `npm audit --omit=dev` before submitting.
5. For mouse, focus or window-lifecycle changes, also run `npm run test:live` and record exact pointer/frontmost-application evidence.
6. Do not commit local agent records, runtime state, screenshots, credentials, absolute home paths or generated dependencies.

## Pull requests

Keep each pull request focused. Describe the behavior change, target applications, test evidence, permission impact and rollback. Security-sensitive findings must follow [SECURITY.md](SECURITY.md), not a public issue or pull request.

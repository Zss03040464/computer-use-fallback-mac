# GitHub repository publication

Date: 2026-07-14
Status: publication ready; remote replacement pending

## Goal

Publish a private, professionally structured GitHub snapshot without local continuity records, machine paths, runtime state or credentials.

## Acceptance requirements

- Remote repository remains private.
- Remote `main` contains only the curated product tree and one clean publication root.
- Local agent/session/history files remain available locally but are not tracked in the publication tree.
- Repository hygiene is enforced by automated tests and CI.
- Standard security, contribution, conduct, changelog, provenance and dependency automation files exist.
- Deterministic product tests, clean-install smoke, dependency audit and publication scans pass.
- The internal-named remote branch is removed only after clean `main` verification.

## Evidence

- Red phase: `node --test tests/node/repository-hygiene.test.mjs` failed because the standard repository surface was absent.
- Green phase: the same test passes with two checks covering the publication contract and repository-relative Markdown links.
- `npm test`: 89 Python, 22 Node and 2 controlled integration tests pass.
- `npm run test:clean-install`: clean-copy installation, concurrent bootstrap and MCP handshake pass.
- `npm audit --omit=dev`: zero known production dependency vulnerabilities.
- `node --check`, Python `compileall`, Ruby YAML parsing and `git diff --cached --check` pass.
- The full local development history remains local; the remote update must use an orphan snapshot and force-with-lease against the previously verified remote head.

# Security Policy

## Supported version

Security fixes are applied to the current `main` branch. This repository is pre-1.0 and does not currently maintain security-fix branches for older snapshots.

## Reporting a vulnerability

Do not publish credentials, exploit details, private application data or screenshots in a normal issue.

Use GitHub's private vulnerability reporting or Security Advisory flow for this repository. Include the affected commit, macOS version, reproduction steps, impact and the smallest safe proof of concept. If private reporting is unavailable, contact the repository owner through a private GitHub channel before disclosing details.

Reports involving Accessibility permissions, Screen Recording, process targeting, focus isolation, unintended foreground delivery or credential exposure are treated as security-sensitive.

## Security boundary

This component requires macOS Accessibility and Screen Recording permissions to perform its intended work. Those permissions are powerful. Run only reviewed commits, keep the repository private until provenance review is complete, and grant permissions only to the exact local runtime being used.

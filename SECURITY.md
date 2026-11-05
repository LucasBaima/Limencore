# Security Policy

Limencore handles personal thoughts. We treat security as part of the product, not an afterthought, and we appreciate anyone who helps keep it safe.

## Supported versions

Limencore is pre-1.0. Only the latest release on the `main` branch receives security fixes.

| Version | Supported |
|---|---|
| latest (`main`) | yes |
| older | no |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub: go to the **Security** tab of this repository and click **Report a vulnerability**. Only the maintainers can see the report.

Please include:
- what the problem is and where (file and line, if you know);
- how to reproduce it (steps or a minimal test case);
- the impact you think it has.

## What to expect

- Acknowledgement within **7 days**.
- An initial assessment within **14 days**, telling you whether we confirmed the issue and what happens next.
- A fix released as soon as reasonably possible, with credit to you in the release notes if you want it.

We ask that you give us a reasonable time to fix the issue before disclosing it publicly.

## Scope

In scope: the code in this repository (the `limencore` package, its storage, validation and public API).

Out of scope: third-party dependencies (report those upstream), and any application built on top of Limencore by other people.

## Good faith

If you act in good faith — no access to other people's data, no service disruption, no public disclosure before a fix — we will not pursue any action against you and will work with you to resolve the issue.
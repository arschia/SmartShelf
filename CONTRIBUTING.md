# Contributing

Start with [setup](docs/SETUP.md), [architecture](docs/ARCHITECTURE.md), the [model card](docs/MODEL_CARD.md) and [testing](docs/TESTING.md).

1. Create a focused branch from `main`.
2. Keep real store data and private configuration out of commits.
3. Preserve the separation between WebRTC preview, inference transport and server-side accounting.
4. Add a meaningful regression test for state/accounting, device authentication or reconnection changes.
5. Run relevant UI harnesses and backend tests, plus source/path checks.
6. Describe the user-visible trigger, resulting behavior and validation in a pull request.

Do not claim detector accuracy from screenshots or annotation counts. Report data provenance, train/test split and environment coverage for any new model. Keep third-party notices and applicable model/asset licenses with redistributed files.

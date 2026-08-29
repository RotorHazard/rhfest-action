# Changelog

This changelog highlights user-facing changes in RHFest. The complete list of merged pull requests remains available in the corresponding GitHub release.

## [Unreleased]

## [3.2.0] - 2026-08-29

### Added

- Added an official Docker-based pre-commit hook. Plugin authors can now pin an RHFest release in `.pre-commit-config.yaml` and run the same validation during commits, pushes, and manual checks.
- Added rule selection and suppression through `select` and `ignore` Action inputs, equivalent environment variables, and local command-line options.
- Added validation for the plugin entry point and its `initialize(rhapi)` function.
- Added detection of private RHAPI race-context access, including access through simple aliases.

### Changed

- The GitHub Action now builds RHFest from the Dockerfile included in the selected Action revision. This makes testing or returning to an older RHFest release independent of a separately moving container tag.
- Validation now reports stable rule codes and consistently formatted local and GitHub Actions diagnostics.

### Fixed

- Invalid manifest JSON is now reported as a regular RHFest diagnostic instead of ending validation with a Python traceback.

## [3.1.0] - 2026-07-11

### Added

- Added dedicated validation for the plugin domain in `manifest.json`.

## [3.0.1] - 2026-03-26

### Changed

- Updated the RHFest runtime and build validation to support Python 3.14.

## [3.0.0] - 2025-06-05

### Removed

- Removed `category` validation from RHFest. Plugin categories are now managed by the RotorHazard community-plugins repository.

## [2.1.2] - 2025-04-17

### Changed

- Refined the manifest validation patterns for more consistent validation of versioned values and identifiers.

## [2.1.1] - 2025-03-20

### Changed

- Improved the regular expressions used to validate manifest values.

## [2.1.0] - 2025-03-18

### Added

- RHFest now reports the exact version used for a validation run.

## [2.0.1] - 2025-03-13

### Changed

- Optional manifest fields may now explicitly contain `null` values.
- Improved the documented workflow for running RHFest locally with Docker.

## [2.0.0] - 2025-03-09

### Added

- Added support for additional optional manifest fields.

### Changed

- Renamed the `documentation` manifest field to `documentation_uri`.
- Manifest validation now accepts additional fields that RHFest does not know about, allowing plugins to adopt new RotorHazard metadata without waiting for an RHFest update.
- Updated category validation to use the community-plugins category source.

### Removed

- Removed validation for `codeowners`, `tags`, and `zip_release` from the manifest schema.

## [1.3.3] - 2025-03-03

### Fixed

- Improved Docker dependency installation so RHFest builds and runs more reliably.

## [1.3.2] - 2025-03-03

### Fixed

- Fixed repository volume mounting and automatic path detection across GitHub Actions and local Docker environments.

### Changed

- Migrated Docker dependency management to uv.

## [1.3.1] - 2025-03-03

### Fixed

- Corrected the Python base image and optimized dependency installation in the Docker image.

## [1.3.0] - 2025-03-03

### Added

- Added validation for the `category` field in `manifest.json`.

### Changed

- Updated project references from Dutch Drone Squad to RotorHazard.

## [1.2.1] - 2025-02-04

### Changed

- Improved how RHFest locates and performs plugin repository structure validation.

## [1.2.0] - 2025-01-30

### Added

- Added validation for the `zip_release` and `zip_filename` manifest fields.

## [1.1.2] - 2025-01-11

### Fixed

- Fixed repository base-path handling during validation.

## [1.1.1] - 2025-01-11

### Changed

- Improved validation logging and path reporting.

## [1.1.0] - 2025-01-11

### Added

- Added directory structure output to help diagnose manifest discovery problems.

## [1.0.1] - 2025-01-10

### Fixed

- Validation failures now return the correct process exit status to GitHub Actions.

## [1.0.0] - 2025-01-09

### Added

- Initial release of the RHFest GitHub Action with plugin repository structure and manifest validation.
- Added validation logging and GitHub Actions integration.

[Unreleased]: https://github.com/RotorHazard/rhfest-action/compare/v3.2.0...develop
[3.2.0]: https://github.com/RotorHazard/rhfest-action/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/RotorHazard/rhfest-action/compare/v3.0.1...v3.1.0
[3.0.1]: https://github.com/RotorHazard/rhfest-action/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/RotorHazard/rhfest-action/compare/v2.1.2...v3.0.0
[2.1.2]: https://github.com/RotorHazard/rhfest-action/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/RotorHazard/rhfest-action/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/RotorHazard/rhfest-action/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/RotorHazard/rhfest-action/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/RotorHazard/rhfest-action/compare/v1.3.3...v2.0.0
[1.3.3]: https://github.com/RotorHazard/rhfest-action/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/RotorHazard/rhfest-action/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/RotorHazard/rhfest-action/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/RotorHazard/rhfest-action/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/RotorHazard/rhfest-action/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/RotorHazard/rhfest-action/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/RotorHazard/rhfest-action/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/RotorHazard/rhfest-action/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/RotorHazard/rhfest-action/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/RotorHazard/rhfest-action/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/RotorHazard/rhfest-action/releases/tag/v1.0.0

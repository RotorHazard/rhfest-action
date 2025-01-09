# RHFest Action

A reusable GitHub Action that validates `manifest.json` files for RotorHazard plugins. It checks for missing fields, invalid formats, and unsupported values, and logs validation errors directly in GitHub Actions logs using **GitHub-friendly annotations**.

## 🛠️ Features

- ✅ Schema validation for `manifest.json`
- 🚨 GitHub Action annotations for validation errors
- ⚠️ Warnings for missing optional fields or extra fields
- 📋 Validates:
  - **domain** format (e.g., lowercase letters, numbers, underscores)
  - **codeowners** GitHub handle (`@username`)
  - **documentation** URL format
  - **dependencies** in `package==X.Y.Z` format

## 🚀 How to Use

Create a file `.github/workflows/validate.yml` in your plugin repository with the following content:

```yaml
name: Validate Plugin Manifest

on:
  push:
  pull_request:

jobs:
  validate:
    name: Run RHFest validation
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Run RHFest validation
        uses: docker://ghcr.io/dutchdronesquad/rhfest-action:latest
```

## Development

How to setup the development environment.

### Prerequisites

You need the following tools to get started:

- [uv] - A python virtual environment/package manager
- [Python] 3.13 - The programming language

### Installation

1. Clone the repository
2. Install all dependencies with UV. This will create a virtual environment and install all dependencies

```bash
uv sync
```

5. Setup the pre-commit check, you must run this inside the virtual environment

```bash
uv run pre-commit install
```

6. Run the application

```bash
uv run rhfest/core.py
```

### Run pre-commit checks

As this repository uses the [pre-commit][pre-commit] framework, all changes
are linted and tested with each commit. You can run all checks and tests
manually, using the following command:

```bash
uv run pre-commit run --all-files
```

To manual run only on the staged files, use the following command:

```bash
uv run pre-commit run
```

## 🌟 Credits

This project was inspired by:

- Manifest validation in [HACS](https://hacs.xyz/)
- Manifest validation (Hassfest) in [Home Assistant](https://www.home-assistant.io/)

## License

Distributed under the **MIT** License. See [`LICENSE`](LICENSE) for more information.

<!-- LINK -->
[uv]: https://docs.astral.sh/uv/
[Python]: https://www.python.org/
[pre-commit]: https://pre-commit.com/

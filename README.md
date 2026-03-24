# metaflow-backend-kit

[![CI](https://github.com/npow/metaflow-backend-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/npow/metaflow-backend-kit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/metaflow-backend-kit)](https://pypi.org/project/metaflow-backend-kit/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-mintlify-18a34a?style=flat-square)](https://mintlify.com/npow/metaflow-backend-kit)

Ship a Metaflow compute backend without reading the plugin source code.

## The problem

Metaflow's compute backend protocol has ~10 interacting hooks across a step decorator, a CLI entry point, and an executor — with no scaffolding, no static validation, and pitfalls that only manifest at runtime inside a remote container. Import paths are one dot off, retry counts need 0-indexing, credentials disappear when env is mutated, and the plugin registration file references modules that don't exist yet. Every backend author re-discovers the same set of bugs.

## Quick start

```bash
pip install metaflow-backend-kit

# Generate the skeleton for a new backend
metaflow-backend-scaffold mybackend

# Fill in the TODO sections in mybackend/mybackend_executor.py, then:
metaflow-backend-validate mybackend/
metaflow-backend-test --backend mybackend
```

## Install

```bash
pip install metaflow-backend-kit

# With dev dependencies (for running compliance tests locally)
pip install "metaflow-backend-kit[dev]"
```

## Usage

### Scaffold a new backend

```bash
metaflow-backend-scaffold mybackend
```

Generates six files:

```
mybackend/
  mybackend_decorator.py   # StepDecorator with all required hooks
  mybackend_executor.py    # Job submission, log streaming, wait
  mybackend_cli.py         # CLI entry point registered in plugins/__init__.py
  mybackend_client.py      # Thin wrapper around your backend SDK
  plugins/__init__.py      # Plugin registration (STEP_DECORATORS_DESC, CLIS_DESC)
  ux-tests-mybackend.yml   # GitHub Actions compliance workflow
```

### Validate without running tests

```bash
metaflow-backend-validate mybackend/
```

Runs 16 static checks — wrong relative import paths, hardcoded retry counts, missing `METAFLOW_EXIT_DISALLOW_RETRY`, credential env-var capture, and more — before you spin up any compute.

```
✓  extension registration exists
✓  SUPPORTED_CAPABILITIES declared
✓  retry_count not hardcoded
✓  retry_count not decremented
✓  METAFLOW_RUNTIME_ENVIRONMENT set
✓  METAFLOW_EXIT_DISALLOW_RETRY used
⚠  metadata sync present
   No metadata sync found. Local metadata may not reach the service.
   → See docs/pitfalls/metadata-sync.md
...
Results: 15 passed, 1 warned
```

### Run compliance tests against a live backend

```bash
metaflow-backend-test --backend mybackend

# Test optional capabilities
metaflow-backend-test --backend mybackend --supported-caps GPU,TIMEOUT
```

Each test targets a specific capability (env propagation, retry semantics, artifact persistence, log streaming) and explains exactly what broke and why.

## How it works

**Scaffold** generates Python from templates that embed all correct Metaflow conventions — two-dot relative import paths, 0-indexed retry counts, `_INITIAL_AUTH_ENV` capture at module load time, `setdefault` env-var merging to avoid clobbering `@environment`. The generated files compile on Python 3.8+.

**Validate** runs 16 regex-based static checks with comment stripping. It catches the most common pitfalls without requiring a live backend or real credentials.

**Compliance** uses `metaflow.Runner` with decospecs to apply your decorator to reference flows, then asserts exact artifact values, log presence, retry semantics, and metadata visibility via the Metaflow client API.

## Pitfall guides

Detailed explanations for each common mistake live in [`docs/pitfalls/`](docs/pitfalls/):

- `retry-count-indexing.md` — 0-indexed vs 1-indexed backend counters
- `credentials-import-time.md` — why `os.environ` inside `step_init` is wrong
- `metadata-sync.md` — syncing task metadata before the container exits
- `infra-vs-step-exit-code.md` — `METAFLOW_EXIT_DISALLOW_RETRY` vs real exit codes
- `conda-remote-commands.md` — linux-64 package resolution from macOS
- `resources-merge.md` — `@resources` + your decorator with `max()` per field

## Development

```bash
git clone https://github.com/npow/metaflow-backend-kit
cd metaflow-backend-kit
pip install -e ".[dev]"

# Run the validator against itself
metaflow-backend-validate metaflow_backend_kit/scaffold/

# Run compliance tests (requires a live backend)
metaflow-backend-test --backend <your-backend>
```

## License

[Apache 2.0](LICENSE)

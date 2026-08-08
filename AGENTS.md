# Repository Guidelines

## Project Structure & Module Organization

FLiberator is a Python 3.12+ package that converts Florida’s Rocket NXT bulk-law data into HTML and JSON. Production code lives in `src/fliberator/`: `download.py` fetches data, `depage.py` reconstructs documents, `decode.py` decodes content, and `emit.py` writes output. Supporting modules cover footnotes, ordering, indexing, and the CLI.

Tests live in `tests/` and generally mirror module names (for example, `tests/test_decode.py`). `scripts/` contains research and validation harnesses, not package code. Format documentation is in `docs/nxt-format.md`; phase history is in `plans/re-plan.md`. Generated `download/` and `output/` directories are ignored.

## Build, Test, and Development Commands

Use `uv` for dependencies and execution; avoid running a bare Python interpreter from the repository root.

```bash
uv sync                         # create/update the development environment
uv run pytest                   # run the complete test suite
uv run pytest tests/test_emit.py # run one test module
uv run ruff check .             # lint imports and code quality
uv run ruff format .            # apply formatting
uv run fliberate                # decode an existing download/ edition
uv run fliberate --download     # fetch, extract, and decode the latest edition
```

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and uppercase names for constants. Ruff enforces a 100-character line length and checks `E`, `F`, import ordering, `UP`, and `B` rules. Format with `uv run ruff format .` and resolve lint findings before submitting changes. Keep validation checks explicit: malformed source data must raise a clear error rather than silently producing output.

## Testing Guidelines

Use `pytest` and place focused tests in `tests/test_<module>.py`; name cases `test_<behavior>()`. Add regression coverage for parser, page-geometry, HTML, metadata, or ordering changes. Run the relevant test file while iterating, then run `uv run pytest` and Ruff. Avoid requiring the large downloaded corpus in ordinary unit tests.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries, often with a scoped prefix, such as `README: lead with install and how to run it` or `Close the three gaps Phase 9 left open`. Keep commits narrowly focused. Pull requests should explain the behavioral change, identify affected output or validation artifacts, link relevant issues or phases when applicable, and include sample output or screenshots when rendered HTML changes.

## Data and Documentation Care

Treat frozen reference data as read-only. Do not commit generated downloads or output. Before revisiting NXT format assumptions, consult `docs/nxt-format.md` and append new findings rather than replacing established research history.

# Releasing FLiberator

## One-time setup

Create accounts on [TestPyPI](https://test.pypi.org/account/register/) and
[PyPI](https://pypi.org/account/register/), verify their email addresses, and
configure a Trusted Publisher on each index:

- Owner: `anseljh`
- Repository: `FLiberator`
- Workflow: `publish.yml`
- Environment: `testpypi` on TestPyPI and `pypi` on PyPI

Use PyPI’s pending-publisher option if `fliberator` has not been published yet.
In GitHub, create the `pypi` environment and require manual approval so the
production upload only follows the TestPyPI smoke test.

## Release procedure

1. Update `__version__` in `src/fliberator/__init__.py` and add a dated entry
   to `CHANGELOG.md`.
2. Run `uv sync --all-groups` and `uv run python scripts/release_check.py`.
3. Merge the release commit, then create and push an exact matching tag, such
   as `v0.1.1` for version `0.1.1`.
4. The `Publish to PyPI` workflow builds once, uploads the artifacts to
   TestPyPI, installs the TestPyPI package, and waits for approval before
   publishing those same artifacts to PyPI.

Published version files are immutable on both indexes. If a TestPyPI upload or
production release needs correction, make a new version rather than rebuilding
or retagging the existing one.

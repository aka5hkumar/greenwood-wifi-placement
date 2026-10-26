"""Import tests for the Vercel serverless entrypoints in api/.

These load each api/*.py the way Vercel's Python runtime does: as a module
by file path, with neither the api/ directory nor the repo root already on
sys.path. A plain `import api.geocode` would NOT catch the failure mode
these guard against — the api/ directory being missing from sys.path, which
broke `from _respond import respond` in production while passing locally.
"""

import importlib.util
import os
import sys

import pytest

API_DIR = os.path.join(os.path.dirname(__file__), "..", "api")
ENTRYPOINTS = ["geocode", "boundary", "compute"]


def _load_isolated(name: str):
    """Load api/<name>.py by path, without pre-seeding sys.path."""
    path = os.path.join(API_DIR, f"{name}.py")
    original = list(sys.path)
    try:
        # Drop any entry that would make api/'s helpers importable for free,
        # so the module has to set up its own sys.path like it must on Vercel.
        api_abs = os.path.abspath(API_DIR)
        sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != api_abs]
        spec = importlib.util.spec_from_file_location(f"_vercel_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original


@pytest.mark.parametrize("name", ENTRYPOINTS)
def test_entrypoint_imports_without_api_dir_on_syspath(name):
    _load_isolated(name)


@pytest.mark.parametrize("name", ENTRYPOINTS)
def test_entrypoint_exports_handler(name):
    """Vercel requires a top-level `handler` (a BaseHTTPRequestHandler subclass)."""
    from http.server import BaseHTTPRequestHandler

    module = _load_isolated(name)
    assert hasattr(module, "handler"), f"api/{name}.py must export `handler`"
    assert issubclass(module.handler, BaseHTTPRequestHandler)

"""Structural smoke test for /reference-data router.

Imports the router and asserts it registers the five expected endpoints
(POST, GET list, GET one, PUT, DELETE). Avoids TestClient deliberately —
the service layer is exhaustively tested in test_service.py and the router
is a thin delegate, so verifying the registration shape here is enough
without dragging the full FastAPI app into the test surface.
"""

import pytest


@pytest.mark.unit
def test_reference_data_router_registers_all_five_crud_endpoints():
    from src.core.components.reference_data.router import router

    assert router.prefix == "/reference-data"

    # Collect (path, method) pairs across the registered routes.
    registered: set[tuple[str, str]] = set()
    for route in router.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        for m in methods:
            registered.add((path, m))

    assert ("/reference-data", "POST") in registered
    assert ("/reference-data", "GET") in registered
    assert ("/reference-data/{short_code}", "GET") in registered
    assert ("/reference-data/{short_code}", "PUT") in registered
    assert ("/reference-data/{short_code}", "DELETE") in registered

"""Smoke tests that the v3 studio routes register correctly on the
FastAPI app + return the expected paths.

End-to-end HTTP tests (multipart upload, full composer flow) need
the full stack (LLM + R2 + DB) and live separately.
"""

import pytest


@pytest.fixture(scope="module")
def app():
    from src.main import app
    return app


@pytest.mark.unit
def test_v3_studio_router_registered(app):
    v3_paths = {
        r.path
        for r in app.routes
        if hasattr(r, "path") and r.path.startswith("/api/v3/studio")
    }
    assert v3_paths, "No /api/v3/studio routes registered — router not mounted"


@pytest.mark.unit
def test_composer_parse_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path") and r.path == "/api/v3/studio/composer/parse"
    ]
    assert len(matches) == 1
    assert "POST" in matches[0].methods


@pytest.mark.unit
def test_composer_generate_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path") and r.path == "/api/v3/studio/composer/generate-template"
    ]
    assert len(matches) == 1
    assert "POST" in matches[0].methods


@pytest.mark.unit
def test_composer_regenerate_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path")
        and r.path == "/api/v3/studio/templates/{template_id}/composer/regenerate-template"
    ]
    assert len(matches) == 1
    assert "PUT" in matches[0].methods


@pytest.mark.unit
def test_templates_list_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path") and r.path == "/api/v3/studio/templates"
    ]
    assert len(matches) == 1
    assert "GET" in matches[0].methods


@pytest.mark.unit
def test_templates_get_route_exists(app):
    # GET + DELETE both bind to /templates/{template_id}; FastAPI registers
    # them as separate Route objects sharing the same path.
    methods_union: set[str] = set()
    for r in app.routes:
        if hasattr(r, "path") and r.path == "/api/v3/studio/templates/{template_id}":
            methods_union |= r.methods or set()
    assert "GET" in methods_union


@pytest.mark.unit
def test_template_field_patch_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path")
        and r.path == "/api/v3/studio/templates/{template_id}/fields/{field_id}"
    ]
    assert len(matches) == 1
    assert "PATCH" in matches[0].methods


@pytest.mark.unit
def test_template_bundling_config_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path")
        and r.path == "/api/v3/studio/templates/{template_id}/bundling-config"
    ]
    assert len(matches) == 1
    assert "PUT" in matches[0].methods


@pytest.mark.unit
def test_template_delete_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path") and r.path == "/api/v3/studio/templates/{template_id}"
    ]
    # GET + DELETE share the same path; assert DELETE is present.
    methods_union: set[str] = set()
    for m in matches:
        methods_union |= m.methods or set()
    assert "DELETE" in methods_union


@pytest.mark.unit
def test_dry_run_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path")
        and r.path == "/api/v3/studio/templates/{template_id}/dry-run"
    ]
    assert len(matches) == 1
    assert "POST" in matches[0].methods


@pytest.mark.unit
def test_dry_run_resume_route_exists(app):
    matches = [
        r for r in app.routes
        if hasattr(r, "path")
        and r.path == "/api/v3/studio/templates/{template_id}/dry-run/resume"
    ]
    assert len(matches) == 1
    assert "POST" in matches[0].methods


@pytest.mark.unit
def test_no_v3_routes_collide_with_v2(app):
    """Sanity check: no v3 path accidentally overlaps a v2 path."""
    v2_paths = {
        r.path for r in app.routes
        if hasattr(r, "path") and r.path.startswith("/api/v2")
    }
    v3_paths = {
        r.path for r in app.routes
        if hasattr(r, "path") and r.path.startswith("/api/v3")
    }
    # No literal path overlap (different prefixes guarantee this)
    assert not (v2_paths & v3_paths)

"""Smoke tests that confirm the v2 repositories import cleanly + expose
the expected public surface. DB-integration tests for create / list /
update / delete live separately (need a test Postgres harness).
"""

import inspect

import pytest


@pytest.mark.unit
def test_templates_v2_repo_exposes_expected_methods():
    from src.core.studio_v2.repositories import TemplatesV2Repository

    expected = {"create", "get", "list", "update", "update_published_snapshot", "soft_delete"}
    actual = {
        name
        for name, fn in inspect.getmembers(TemplatesV2Repository, predicate=inspect.ismethod)
    }
    missing = expected - actual
    assert not missing, f"Missing methods on TemplatesV2Repository: {missing}"


@pytest.mark.unit
def test_template_fields_v2_repo_exposes_expected_methods():
    from src.core.studio_v2.repositories import TemplateFieldsV2Repository

    expected = {"create_many", "list_for_template", "get", "patch_params", "re_extract_diff_apply"}
    actual = {
        name
        for name, fn in inspect.getmembers(TemplateFieldsV2Repository, predicate=inspect.ismethod)
    }
    missing = expected - actual
    assert not missing, f"Missing methods on TemplateFieldsV2Repository: {missing}"


@pytest.mark.unit
def test_orm_models_register_on_package_import():
    """Importing the package side-effects an import of `models` so the
    ORM classes register against the shared Base.metadata. Verify the
    tables show up in Base.metadata.tables.
    """
    import src.core.studio_v2.repositories  # noqa: F401
    from src.chatbot.models import Base

    assert "templates_v2" in Base.metadata.tables
    assert "template_fields_v2" in Base.metadata.tables


@pytest.mark.unit
def test_templates_v2_table_columns():
    from src.core.studio_v2.repositories.models import TemplateV2

    expected_cols = {
        "id", "firm_id", "name", "config",
        "original_doc_url", "template_doc_url",
        "published_at", "published_spec",
        "created_at", "updated_at", "is_active",
    }
    actual_cols = {c.name for c in TemplateV2.__table__.columns}
    assert actual_cols == expected_cols, f"Column mismatch: {actual_cols ^ expected_cols}"


@pytest.mark.unit
def test_template_fields_v2_table_columns():
    from src.core.studio_v2.repositories.models import TemplateFieldV2

    expected_cols = {
        "id", "template_id",
        "template_variable", "template_property_marker",
        "template_property_marker_aliases", "template_identifying_text_match",
        "description", "template_index", "params",
        "created_at", "updated_at",
    }
    actual_cols = {c.name for c in TemplateFieldV2.__table__.columns}
    assert actual_cols == expected_cols, f"Column mismatch: {actual_cols ^ expected_cols}"


@pytest.mark.unit
def test_template_fields_v2_fk_cascade_on_delete():
    """FK to templates_v2 with ON DELETE CASCADE."""
    from src.core.studio_v2.repositories.models import TemplateFieldV2

    fks = list(TemplateFieldV2.__table__.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "templates_v2"
    assert fk.ondelete == "CASCADE"


@pytest.mark.unit
def test_template_fields_v2_unique_constraint_on_variable():
    """Unique on (template_id, template_variable) so two fields can't
    collide on name within the same template."""
    from src.core.studio_v2.repositories.models import TemplateFieldV2

    unique_indexes = [
        idx for idx in TemplateFieldV2.__table__.indexes if idx.unique
    ]
    assert any(
        {c.name for c in idx.columns} == {"template_id", "template_variable"}
        for idx in unique_indexes
    )

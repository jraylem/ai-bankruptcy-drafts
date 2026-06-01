"""SQLAlchemy ORM models for the studio_v2 namespace.

Two tables ship in Phase 1:
- `templates_v2` — per-template row holding the working draft config + the
  published snapshot. Mirrors the relevant subset of v1's `DraftTemplate`
  but drops `template_spec` (lives relationally in `template_fields_v2`)
  and `agent_config` (lives in `published_spec` JSONB on publish).
- `template_fields_v2` — per-variable working-draft row. FK to
  templates_v2; unique on (template_id, template_variable).

`drafts_v2` lands in Phase 3 and is NOT in this file.

All columns are designed to mirror v1's storage conventions: `String`
PKs holding UUID strings, `JSONB` for nested structures, `created_at`
+ `updated_at` timestamps via `server_default=func.now()` /
`onupdate=func.now()`, soft-delete via `is_active`. Uses the shared
`src.chatbot.models.Base` so alembic-free migrations and v1 share the
same metadata registry.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from src.chatbot.models import Base


class TemplateV2(Base):
    """v2 template — per-template row.

    Phase 1 stores:
    - identity + display (id, name)
    - bundling config (TemplateConfigV2 as JSONB: role + companions)
    - docx storage refs (R2 keys returned by the composer)
    - publish gate (published_at + published_spec) — Phase 3 populates
      these via the Publish endpoint; they sit NULL throughout Phase 1.

    Intentionally LACKS:
    - `template_spec` JSONB (working draft lives relationally in
      template_fields_v2)
    - `agent_config` JSONB (implicit in published_spec once published)
    - `schema_version` flag (v1 + v2 are independent products; no
      shared discriminator)
    """
    __tablename__ = "templates_v2"

    id = Column(String, primary_key=True)
    firm_id = Column(String, nullable=True, index=True)
    name = Column(String(255), nullable=False)

    # TemplateConfigV2 JSONB: { role, companions[] }
    config = Column(JSONB, nullable=False, server_default="""{"role": "single", "companions": []}""")

    # R2 keys / presigned URLs returned by the composer.
    original_doc_url = Column(Text, nullable=True)
    template_doc_url = Column(Text, nullable=True)

    # Publish gate. NULL until first publish. published_spec is the
    # FROZEN TemplateSpecV2 JSONB used by Phase 3 drafting (immutable
    # until next /publish). has_unpublished_changes is COMPUTED, not
    # stored — derived from (updated_at > published_at).
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_spec = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("idx_templates_v2_name", "name"),
        Index(
            "idx_templates_v2_firm_id",
            "firm_id",
            postgresql_where=Column("firm_id").isnot(None),
        ),
        Index("idx_templates_v2_published", "published_at", postgresql_where=Column("published_at").isnot(None)),
    )


class TemplateFieldV2(Base):
    """v2 template field — per-variable working-draft row.

    One row per template variable; FK to templates_v2 with cascade
    delete. Unique on (template_id, template_variable). `params` holds
    the WizardSourceParams JSONB (the wizard's saved source binding);
    NULL until the paralegal touches the field OR until TemplateAgentV2
    pre-populates a source-suggestion default at composer time.
    """
    __tablename__ = "template_fields_v2"

    id = Column(String, primary_key=True)
    template_id = Column(
        String,
        ForeignKey("templates_v2.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Variable identity (set by composer; mostly immutable).
    template_variable = Column(String(255), nullable=False)
    template_property_marker = Column(Text, nullable=True)
    template_property_marker_aliases = Column(JSONB, nullable=True)
    template_identifying_text_match = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    template_index = Column(Integer, nullable=False, default=0)

    # Wizard-saved WizardSourceParams JSONB. NULL until set by
    # TemplateAgentV2 (composer default) or the paralegal (wizard save).
    params = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        Index(
            "uq_template_fields_v2_variable",
            "template_id",
            "template_variable",
            unique=True,
        ),
        Index("idx_template_fields_v2_template_index", "template_id", "template_index"),
    )

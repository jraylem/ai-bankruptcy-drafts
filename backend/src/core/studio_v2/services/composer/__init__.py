"""Studio V2 composer — parse / generate / regenerate flow.

Three public operations mirroring v1's `src/core/components/engines/template/composer.py`:

    parse_document_v2(filename, file_content)
        Flatten a .docx upload to text for TemplateAgentV2.

    generate_template_v2(name, parsed_doc, file_content, ...)
        Run TemplateAgentV2, build the placeholder-marked template.docx
        via DocxTemplateService.create_template (read-only import),
        upload original + template to R2 under `template_v2/{id}/`,
        persist templates_v2 row + template_fields_v2 rows.

    regenerate_template_v2(template_id, ignored_texts, merges, ...)
        Re-extract on regeneration; diff against existing
        template_fields_v2 rows preserving wizard-saved `params`.

Skip the v1 `compose_agent_config` equivalent — v2 has no separate
"compose" step. Validate-and-snapshot happens at Phase 3 publish.
"""

from .generate import generate_template_v2
from .parse import parse_document_v2
from .publish import publish_template_v2
from .regenerate import regenerate_template_v2
from .schemas import (
    DocumentParseResponseV2,
    MergeOperationV2,
    TemplateGenerateResponseV2,
    TemplateRegenerateDiffV2,
)

__all__ = [
    "DocumentParseResponseV2",
    "MergeOperationV2",
    "TemplateGenerateResponseV2",
    "TemplateRegenerateDiffV2",
    "generate_template_v2",
    "parse_document_v2",
    "publish_template_v2",
    "regenerate_template_v2",
]

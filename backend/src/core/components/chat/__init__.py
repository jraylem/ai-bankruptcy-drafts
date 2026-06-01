"""v2 case chat — agentic streaming chat scoped to (user, case).

Owns the /chat/* HTTP surface plus the orchestration glue between the
router, the persistence layer (CaseSession + CaseSessionMessage), and the
streaming agent in `src.core.agents.llm.chat`. Tool extensibility lives
under that agent package — drop new tools into `agents/llm/chat/tools/`,
decorate with `@register_tool`, and they are picked up automatically.

NOTE: the APIRouter object is intentionally NOT re-exported from this
package — importing it would shadow the `.router` submodule on the
package, breaking `from src.core.components.chat import router` (which
would yield the APIRouter, not the submodule). Callers should import
explicitly: `from src.core.components.chat.router import router`.
"""

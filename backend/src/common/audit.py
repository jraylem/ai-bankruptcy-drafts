"""Shared audit log utility — Phase 4 Settings.

Fire-and-forget helper imported by any service that needs to record a
firm-level security or admin event. Errors are swallowed so a failed
audit write never blocks the main request.

Actions written by this helper:
  member.invited          firms/service.invite_member()
  member.joined           firms/service.accept_invitation()
  member.removed          firms/service.remove_member()
  case.accepted           core/components/case_inbox/service.accept()
  settings.firm_updated   settings/service.update_firm_settings()
  security.password_changed  settings/service.change_password()
  security.session_revoked   settings/service.revoke_session()
  security.all_sessions_revoked  settings/service.revoke_all_sessions()
  billing.subscription_changed   billing/webhook handler
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def log_audit_event(
    firm_id: str,
    action: str,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Write one row to audit_logs. Never raises — errors are logged and swallowed."""
    try:
        from ..auth.database import UserAsyncSessionLocal
        from ..settings.models import AuditLog

        async with UserAsyncSessionLocal() as session:
            session.add(AuditLog(
                id=str(uuid.uuid4()),
                firm_id=firm_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                event_data=metadata,
                created_at=datetime.now(timezone.utc),
            ))
            await session.commit()
    except Exception as exc:
        logger.warning(f"[audit] failed to log action={action!r} firm={firm_id!r}: {exc}")

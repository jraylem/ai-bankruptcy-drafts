"""Transactional email functions via Resend.

All functions are fire-and-forget async wrappers around the Resend SDK.
Templates are Jinja2 HTML files in src/notifications/templates/.

Called by:
  - src/auth/service.py (register_new_user)
  - src/firms/service.py (invite_member, accept_invitation, transfer_ownership)
  - src/billing/ (Phase 2: subscription events)
"""

import asyncio
import logging
from pathlib import Path
from urllib.parse import quote
from jinja2 import Environment, FileSystemLoader, select_autoescape
import resend

from ..config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **ctx) -> str:
    """Render a Jinja2 HTML template with the given context."""
    return _jinja_env.get_template(template_name).render(**ctx)


def _send_sync(to: str, subject: str, html: str) -> None:
    """Blocking Resend API call — must be called via asyncio.to_thread."""
    resend.api_key = settings.EMAIL_API_KEY
    resend.Emails.send({
        "from": settings.EMAIL_FROM_ADDRESS,
        "to": [to],
        "subject": subject,
        "html": html,
    })


async def _send(to: str, subject: str, html: str) -> None:
    """Send email via Resend. Errors are logged without raising so callers always succeed."""
    try:
        await asyncio.to_thread(_send_sync, to, subject, html)
    except Exception as e:
        logger.error(f"Failed to send email to {to!r} (subject={subject!r}): {e}")


# ---------------------------------------------------------------------------
# Auth emails (Phase 3 — registration update)
# ---------------------------------------------------------------------------

async def send_email_verification_email(
    to_email: str,
    verification_token: str,
    firm_name: str = "",
) -> None:
    """Email verification on registration.

    Called by: src/auth/routes.register_user() via BackgroundTasks
    """
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
    if firm_name:
        verify_url += f"&firm_name={quote(firm_name)}"
    html = _render(
        "email_verification.html",
        verify_url=verify_url,
    )
    await _send(to_email, "Verify your Jurisgentic account", html)


async def send_resend_verification_email(
    to_email: str,
    verification_token: str,
    firm_name: str = "",
) -> None:
    """Re-sent email verification link (distinct subject + template from initial registration).

    Called by: src/auth/routes.resend_verification() via BackgroundTasks
    """
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
    if firm_name:
        verify_url += f"&firm_name={quote(firm_name)}"
    html = _render(
        "email_verification_resend.html",
        verify_url=verify_url,
    )
    await _send(to_email, "Your new Jurisgentic verification link", html)


# ---------------------------------------------------------------------------
# Firm management emails (Phase 3)
# ---------------------------------------------------------------------------

async def send_invite_email(
    to_email: str,
    inviter_name: str,
    firm_name: str,
    invite_token: str,
) -> None:
    """Invitation to join a firm.

    Called by: src/firms/service.invite_member()
    """
    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={invite_token}&firm_name={quote(firm_name)}"
    html = _render(
        "invite.html",
        inviter_name=inviter_name,
        firm_name=firm_name,
        invite_url=invite_url,
    )
    await _send(to_email, f"You've been invited to join {firm_name} on Jurisgentic", html)


async def send_invitation_accepted_email(
    to_email: str,
    new_member_name: str,
    firm_name: str,
) -> None:
    """Notifies the inviter that their invitation was accepted.

    Called by: src/firms/service.accept_invitation()
    """
    html = _render(
        "invitation_accepted.html",
        new_member_name=new_member_name,
        firm_name=firm_name,
        dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    await _send(to_email, f"{new_member_name} has joined {firm_name}", html)


async def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """Password reset link.

    Called by: POST /api/auth/forgot-password (via auth/routes.py) via BackgroundTasks
    """
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    html = _render("password_reset.html", reset_url=reset_url)
    await _send(to_email, "Reset your Jurisgentic password", html)


# ---------------------------------------------------------------------------
# Billing emails (Phase 2 calls these from src/billing/)
# ---------------------------------------------------------------------------

async def send_subscription_activated_email(
    to_email: str,
    firm_name: str,
    plan_name: str,
) -> None:
    """Subscription activated / trial converted.

    Called by: src/billing/ Stripe webhook handler
    """
    html = _render(
        "subscription_activated.html",
        firm_name=firm_name,
        plan_name=plan_name,
        dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    await _send(to_email, f"Your {plan_name} subscription is now active", html)


async def send_subscription_canceled_email(to_email: str, firm_name: str) -> None:
    """Subscription canceled.

    Called by: src/billing/ Stripe webhook handler
    """
    html = _render(
        "subscription_canceled.html",
        firm_name=firm_name,
        dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    await _send(to_email, "Your Jurisgentic subscription has been canceled", html)


async def send_payment_failed_email(
    to_email: str,
    firm_name: str,
    portal_url: str,
) -> None:
    """Payment failed — includes link to Stripe billing portal.

    Called by: src/billing/ Stripe webhook handler
    """
    html = _render(
        "payment_failed.html",
        firm_name=firm_name,
        portal_url=portal_url,
    )
    await _send(to_email, "Action required: payment failed for your Jurisgentic subscription", html)


# ---------------------------------------------------------------------------
# User approval emails (waitlist flow)
# ---------------------------------------------------------------------------

async def send_approval_request_email(
    to_email: str,
    user_name: str,
    user_email: str,
    approve_url: str,
    deny_url: str,
    firm_name: str = "",
) -> None:
    """Notify admin that a new user is awaiting access approval.

    Called by: src/auth/service.verify_email_token()
    """
    html = _render(
        "approval_request.html",
        user_name=user_name,
        user_email=user_email,
        firm_name=firm_name,
        approve_url=approve_url,
        deny_url=deny_url,
    )
    await _send(to_email, f"New Jurisgentic sign-up waiting for approval — {user_email}", html)


async def send_user_approved_email(
    to_email: str,
    login_url: str,
) -> None:
    """Notify the registrant that their account has been approved.

    Called by: src/auth/service.approve_user()
    """
    html = _render("user_approved.html", login_url=login_url)
    await _send(to_email, "Your Jurisgentic access has been approved", html)


async def send_user_denied_email(to_email: str) -> None:
    """Notify the registrant that their account was not approved.

    Called by: src/auth/service.deny_user()
    """
    html = _render("user_denied.html")
    await _send(to_email, "Your Jurisgentic registration was not approved", html)


# ---------------------------------------------------------------------------
# Motion emails (future)
# ---------------------------------------------------------------------------

async def send_motion_approved_email(
    to_email: str,
    motion_type: str,
    case_number: str,
) -> None:
    """Motion approved notification.

    Called by: future motion approval workflow
    """
    html = _render(
        "motion_approved.html",
        motion_type=motion_type,
        case_number=case_number,
        dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    await _send(to_email, f"Motion approved — {case_number}", html)


async def send_motion_rejected_email(
    to_email: str,
    motion_type: str,
    case_number: str,
    reason: str,
) -> None:
    """Motion rejected notification.

    Called by: future motion approval workflow
    """
    html = _render(
        "motion_rejected.html",
        motion_type=motion_type,
        case_number=case_number,
        reason=reason,
        dashboard_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    await _send(to_email, f"Motion requires revision — {case_number}", html)

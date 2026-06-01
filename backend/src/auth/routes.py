"""Authentication routes."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from ..chatbot.database import log_user_action
from ..schema import ForgotPasswordRequest, LoginResponse, RegisterResponse, ResendVerificationRequest, ResetPasswordRequest, UserCreate, UserLogin, UserResponse, VerifyEmailRequest
from .auth import (
    get_current_user,
    revoke_refresh_token,
    set_auth_cookies,
    validate_and_rotate_refresh_token,
)
from .models import User
from ..notifications.email import send_email_verification_email, send_password_reset_email, send_resend_verification_email
from .service import login_user, register_new_user, request_password_reset, reset_password, resend_verification_email, review_by_token, verify_email_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")
    response.delete_cookie("csrf_token", path="/")


async def _build_user_response(user: User) -> UserResponse:
    """Build a UserResponse that includes onboarding_status from the firm.

    Used by login, verify-email, refresh, and /me so every auth response
    carries the current onboarding status consistently.
    Null DB values are treated as 'pending'.
    """
    from ..firms.service import get_firm
    onboarding_status = "pending"
    if user.firm_id:
        firm = await get_firm(user.firm_id)
        onboarding_status = firm.onboarding_status or "pending"
    base = UserResponse.from_orm(user)
    return base.model_copy(update={"onboarding_status": onboarding_status})


@router.post("/register", response_model=RegisterResponse)
async def register_user(user_data: UserCreate, background_tasks: BackgroundTasks):
    """Create a new account and send a verification email. No JWT is returned until the email is verified."""
    result, email, token, firm_name = await register_new_user(user_data)
    background_tasks.add_task(send_email_verification_email, email, token, firm_name)
    return result


@router.post("/verify-email", response_model=LoginResponse)
async def verify_email(body: VerifyEmailRequest, request: Request, response: Response):
    """Verify the email token from the registration email.

    On success, sets auth cookies and returns a JWT so the frontend
    can log the user in immediately.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    user, access_token, refresh_token = await verify_email_token(body.token, ip_address=ip, user_agent=ua)
    set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=await _build_user_response(user),
    )


@router.post("/resend-verification")
async def resend_verification(body: ResendVerificationRequest, background_tasks: BackgroundTasks):
    """Resend the email verification link.

    Always returns HTTP 200 with the same message regardless of whether the
    email is registered or already verified — prevents email enumeration.
    """
    result, email, token, firm_name = await resend_verification_email(body.email)
    if email and token:
        background_tasks.add_task(send_resend_verification_email, email, token, firm_name)
    return result


@router.post("/login", response_model=LoginResponse)
async def login(user_credentials: UserLogin, request: Request, response: Response):
    """Authenticate and set HttpOnly session cookies.

    Also returns the access token in the body so the existing frontend
    (Bearer-based) continues to work unchanged during the migration period.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    user, access_token, refresh_token = await login_user(
        user_credentials.email, user_credentials.password, ip_address=ip, user_agent=ua
    )
    set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=await _build_user_response(user),
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(request: Request, response: Response):
    """Rotate the refresh token and issue a new access token.

    Reads the refresh_token HttpOnly cookie — no request body needed.
    """
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    user, new_access, new_refresh = await validate_and_rotate_refresh_token(raw_refresh, ip_address=ip, user_agent=ua)
    set_auth_cookies(response, new_access, new_refresh)
    return LoginResponse(
        access_token=new_access,
        token_type="bearer",
        user=await _build_user_response(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """Revoke the server-side refresh session and clear all auth cookies."""
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        await revoke_refresh_token(raw_refresh)

    _clear_auth_cookies(response)

    await log_user_action(
        action="logout",
        user_id=current_user.id,
        firm_id=current_user.firm_id,
        metadata={"email": current_user.email},
    )
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    """Send a password reset link to the given email address.

    Always returns HTTP 200 with the same message regardless of whether the
    email is registered — prevents email enumeration.
    """
    email, token = await request_password_reset(body.email)
    if email and token:
        background_tasks.add_task(send_password_reset_email, email, token)
    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/reset-password")
async def reset_password_endpoint(body: ResetPasswordRequest):
    """Consume a password reset token and set a new password.

    On success all active refresh sessions are revoked so the user must log in
    again on every device. No cookies are set — the frontend should redirect to
    the login page.
    """
    await reset_password(body.token, body.new_password)
    return {"message": "Password updated. Please log in with your new password."}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return await _build_user_response(current_user)


@router.get("/user-approval/{token}")
async def review_user_approval(
    token: str,
    action: str = Query(..., pattern="^(approve|deny)$"),
):
    """Public endpoint — admin clicks from email to approve or deny a waitlisted user.

    No auth required: the token in the URL is the credential.
    Returns JSON so the frontend page can handle the result.
    """
    await review_by_token(token, action)
    return {"status": action, "message": f"User has been {action}d successfully."}

"""
Gmail API Authentication Module

Handles OAuth2 authentication for Gmail API, including:
- Loading existing tokens
- Refreshing expired tokens
- Running OAuth flow if needed
- Returning credentials for Gmail API service
"""

import os
from pathlib import Path
from typing import Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    GMAIL_API_AVAILABLE = True
except ImportError:
    print("Warning: Gmail API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client")
    Request = None
    Credentials = None
    InstalledAppFlow = None
    GMAIL_API_AVAILABLE = False

# Gmail API scopes needed
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Google Drive API scopes (separate token to avoid invalidating Gmail token)
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']

# File paths
GMAIL_CREDENTIALS_DIR = Path(__file__).resolve().parent
GMAIL_TOKEN_FILE = GMAIL_CREDENTIALS_DIR / "token.json"
GMAIL_CREDENTIALS_FILE = GMAIL_CREDENTIALS_DIR / "credentials.json"
DRIVE_TOKEN_FILE = GMAIL_CREDENTIALS_DIR / "drive_token.json"
REPO_ROOT = Path(__file__).resolve().parents[3]
ECF_DOWNLOADER_DIR = REPO_ROOT / "ecf-petition-downloader"
ECF_TOKEN_FILE = ECF_DOWNLOADER_DIR / "token.json"
ECF_CREDENTIALS_FILE = ECF_DOWNLOADER_DIR / "credentials.json"


def _resolve_first_existing(paths: list[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None


def authenticate_gmail_api(
    credentials_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> Credentials:
    """
    Authenticate with Gmail API using OAuth2.
    
    This function:
    1. Checks for existing token and loads it if valid
    2. Refreshes token if expired
    3. Runs OAuth flow if no valid token exists
    4. Saves token for future use
    
    Args:
        credentials_path: Optional path to OAuth2 credentials JSON file.
                        If None, uses default location (gmail/credentials.json)
    
    Returns:
        Credentials object that can be used to build Gmail API service
    
    Raises:
        ImportError: If Gmail API libraries are not installed
        FileNotFoundError: If credentials.json file is not found
        RuntimeError: If authentication fails
    """
    if not GMAIL_API_AVAILABLE:
        raise ImportError(
            "Gmail API libraries not installed. "
            "Install with: pip install google-auth google-auth-oauthlib google-api-python-client"
        )
    
    creds = None
    credentials_candidates = [
        Path(credentials_path).expanduser().resolve() if credentials_path else None,
        Path(os.getenv("GMAIL_V2_CREDENTIALS_PATH", "")).expanduser().resolve()
        if os.getenv("GMAIL_V2_CREDENTIALS_PATH")
        else None,
        ECF_CREDENTIALS_FILE,
        GMAIL_CREDENTIALS_FILE,
    ]
    credentials_candidates = [path for path in credentials_candidates if path is not None]
    resolved_credentials_path = _resolve_first_existing(credentials_candidates) or credentials_candidates[0]

    token_candidates = [
        Path(token_path).expanduser().resolve() if token_path else None,
        Path(os.getenv("GMAIL_V2_TOKEN_PATH", "")).expanduser().resolve()
        if os.getenv("GMAIL_V2_TOKEN_PATH")
        else None,
        ECF_TOKEN_FILE if resolved_credentials_path == ECF_CREDENTIALS_FILE else None,
        ECF_TOKEN_FILE,
        GMAIL_TOKEN_FILE,
    ]
    token_candidates = [path for path in token_candidates if path is not None]
    resolved_token_path = _resolve_first_existing(token_candidates) or token_candidates[0]
    
    # Create credentials directory if it doesn't exist
    GMAIL_CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if we have a stored token
    if resolved_token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(resolved_token_path), SCOPES
            )
            print(f"[info] Loaded existing Gmail API token: {resolved_token_path}")
        except Exception as e:
            print(f"[warn] Error loading token: {e}")
            creds = None
    
    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            try:
                creds.refresh(Request())
                print("[info] Refreshed Gmail API token")
            except Exception as e:
                print(f"[error] Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            # Need to run OAuth flow
            if not resolved_credentials_path.exists():
                raise FileNotFoundError(
                    f"Gmail credentials file not found. Tried: "
                    f"{', '.join(str(path) for path in credentials_candidates)}\n"
                    "Please download OAuth2 credentials from Google Cloud Console:\n"
                    "1. Go to https://console.cloud.google.com/\n"
                    "2. Create/select a project\n"
                    "3. Enable Gmail API\n"
                    "4. Create OAuth 2.0 credentials\n"
                    f"5. Download credentials.json to: {resolved_credentials_path}"
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(resolved_credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            print("[info] Completed Gmail API OAuth flow")
        
        # Save credentials for next time
        resolved_token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_token_path, 'w') as token:
            token.write(creds.to_json())
        print(f"[info] Saved Gmail API token to {resolved_token_path}")
    
    return creds


def get_gmail_service(
    credentials_path: Optional[str] = None,
    token_path: Optional[str] = None,
):
    """
    Get authenticated Gmail API service.
    
    This is a convenience function that authenticates and builds the service
    in one call.
    
    Args:
        credentials_path: Optional path to OAuth2 credentials JSON file.
                        If None, uses default location (gmail/credentials.json)
    
    Returns:
        Gmail API service object (from googleapiclient.discovery.build)
    
    Raises:
        ImportError: If Gmail API libraries are not installed
        FileNotFoundError: If credentials.json file is not found
        RuntimeError: If authentication or service initialization fails
    """
    from googleapiclient.discovery import build
    
    creds = authenticate_gmail_api(credentials_path, token_path)
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        print("[info] Gmail API service initialized successfully")
        return service
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Gmail API service: {e}")


def authenticate_drive_api() -> "Credentials":
    """Authenticate with Google Drive API using a separate token file."""
    if not GMAIL_API_AVAILABLE:
        raise ImportError("Google API libraries not installed.")

    creds = None
    if DRIVE_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(DRIVE_TOKEN_FILE), DRIVE_SCOPES)
        except Exception as e:
            print(f"[warn] Error loading drive token: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[info] Refreshed Drive API token")
            except Exception as e:
                print(f"[error] Failed to refresh drive token: {e}")
                creds = None

        if not creds:
            if not GMAIL_CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"credentials.json not found at {GMAIL_CREDENTIALS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDENTIALS_FILE), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
            print("[info] Completed Drive API OAuth flow")

        GMAIL_CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(DRIVE_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print(f"[info] Saved Drive token to {DRIVE_TOKEN_FILE}")

    return creds


def get_drive_service():
    """Get authenticated Google Drive API service."""
    from googleapiclient.discovery import build
    creds = authenticate_drive_api()
    return build("drive", "v3", credentials=creds)


def test_authentication(credentials_path: Optional[str] = None) -> bool:
    """
    Test Gmail API authentication.
    
    Args:
        credentials_path: Optional path to OAuth2 credentials JSON file.
                        If None, uses default location (gmail/credentials.json)
    
    Returns:
        True if authentication successful, False otherwise
    """
    try:
        service = get_gmail_service(credentials_path)
        
        # Try to get user profile as a test
        profile = service.users().getProfile(userId='me').execute()
        email_address = profile.get('emailAddress', 'Unknown')
        print(f"[info] Gmail API authentication successful. Connected to: {email_address}")
        return True
    except Exception as e:
        print(f"[error] Gmail API authentication test failed: {e}")
        return False


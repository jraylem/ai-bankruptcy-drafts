"""
Backward-compatible facade for src/gmail/service.py.
All symbols are now defined in src/gmail/service/ package.
Do not add new functions here — add them to the appropriate
module inside src/gmail/service/ and re-export from service/__init__.py.
"""
from .service import *  # noqa: F401, F403

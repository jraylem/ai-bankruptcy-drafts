"""Database configuration for user authentication."""

import os
import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text, func
from ..config import settings
from .models import Base, User
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use NullPool for Taskiq workers to avoid connection-pool issues under concurrent tasks
_is_taskiq_worker = os.environ.get("TASKIQ_WORKER", "").lower() == "true"


def _get_db_url_and_ssl(url: str) -> tuple[str, dict]:
    """Strip SSL params from URL and return clean URL + connect_args for asyncpg."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    ssl_param = query_params.pop("ssl", [None])[0]
    query_params.pop("sslmode", None)

    new_query = urlencode(query_params, doseq=True)
    clean_url = urlunparse(parsed._replace(query=new_query))

    connect_args = {}
    if ssl_param in ("require", "true", "True", "1"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_context

    return clean_url, connect_args


_db_url, _connect_args = _get_db_url_and_ssl(settings.USER_DATABASE_URL)

_engine_kwargs = {
    "echo": False,
    "connect_args": _connect_args,
}

if _is_taskiq_worker:
    _engine_kwargs["poolclass"] = NullPool
    logger.info("Using NullPool for worker (user_engine)")
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 300

# Create async engine for user database
user_engine = create_async_engine(
    _db_url,
    **_engine_kwargs,
)

# Create async session factory for user database
UserAsyncSessionLocal = async_sessionmaker(
    user_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_user_db_session() -> AsyncSession:
    """Get a user database session."""
    return UserAsyncSessionLocal()

async def init_user_db():
    """Initialize user database tables."""
    async with user_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("User database tables created successfully")

async def close_user_db():
    """Close user database connections."""
    await user_engine.dispose()
    logger.info("User database connections closed")

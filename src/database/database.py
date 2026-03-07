from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

try:
    from sqlalchemy_cloudflare_d1 import create_engine_from_binding
    D1_AVAILABLE = True
except ImportError:
    D1_AVAILABLE = False

# This creates a declarative base class for your SQLAlchemy models
Base = declarative_base()

# Local Fallback Execution (Used for `uvicorn` local testing)
SQLALCHEMY_DATABASE_URL = "sqlite:///./agrinow.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session(env):
    """
    Creates a SQLAlchemy engine and local session directly from 
    the Cloudflare D1 environment binding injected into the request.
    This connection is only meant for Cloudflare Workers.
    """
    if D1_AVAILABLE and hasattr(env, "DB"):
        cf_engine = create_engine_from_binding(env.DB)
        CFSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cf_engine)
        return CFSessionLocal()
    else:
        # Fallback to local SQLite if ran without Cloudflare Workers context
        return SessionLocal()

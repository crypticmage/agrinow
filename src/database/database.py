from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

# Load .env relative to this file's path (agrinow/src/database/database.py -> agrinow/.env)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please check your .env file.")

Base = declarative_base()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,     # recycle stale connections
    pool_size=5,            # number of connections to keep open
    max_overflow=10         # maximum overflow connections
)
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")



# Initialize Logfire only if token is provided
if LOGFIRE_TOKEN:
    import logfire
    logfire.instrument_sqlalchemy(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

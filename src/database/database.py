from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# === Primary Database — PostgreSQL on Render ===
# Set DATABASE_URL in your .env (local) or Render environment variables (production)
# Format: postgresql://user:password@host:port/dbname
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/agrinow"  # local fallback
)

Base = declarative_base()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import os
from sqlalchemy import create_engine, Column, BigInteger, String
from sqlalchemy.orm import declarative_base, sessionmaker

# === Supabase PostgreSQL Configuration ===
# Get this from Supabase Dashboard -> Project Settings -> Database -> Connection string -> URI
# DO NOT FORGET TO REPLACE [YOUR-PASSWORD] with your actual db password
SUPABASE_DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL", "postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT].supabase.co:5432/postgres")

# Create Supabase SQLAlchemy Engine
engine = create_engine(SUPABASE_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define the UserKeys Model for Supabase
class UserKeys(Base):
    __tablename__ = "user_keys"
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    encrypted_private_key = Column(String, nullable=False)
    nonce = Column(String, nullable=False)

# Auto-create the table in Supabase Database
Base.metadata.create_all(bind=engine)

async def store_user_keys_in_supabase(
    user_id: int,
    encrypted_private_key: str,
    nonce: str
):
    """
    Inserts the encrypted private key and nonce into the Supabase `user_keys` table
    using SQLAlchemy (exactly like the video).
    """
    db = SessionLocal()
    try:
        new_key = UserKeys(
            user_id=user_id,
            encrypted_private_key=encrypted_private_key,
            nonce=nonce
        )
        db.add(new_key)
        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"SQLAlchemy Supabase insert error: {e}")
    finally:
        db.close()

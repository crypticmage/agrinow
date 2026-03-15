import os
import httpx
from dotenv import load_dotenv

# Load .env relative to this file's path (agrinow/src/database/database.py -> agrinow/.env)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
load_dotenv(env_path)
def _clean_secret(val: str) -> str:
    if not val:
        return val
    return val.encode('ascii', 'ignore').decode('ascii').strip().strip('"').strip("'")

SUPABASE_URL = _clean_secret(os.getenv("SUPABASE_URL"))
SUPABASE_SERVICE_KEY = _clean_secret(os.getenv("SUPABASE_SERVICE_KEY"))


async def store_user_keys_in_supabase(
    user_id: int,
    encrypted_private_key: str,
    nonce: str,
    supabase_url: str = None,
    supabase_key: str = None
):
    """
    Inserts the encrypted private key and nonce into the Supabase `user_keys` table
    via Supabase's PostgREST HTTP API.

    Works on both local uvicorn AND Cloudflare Workers. No psycopg2 needed.

    Supabase Table Schema (run once in Supabase SQL Editor):
        CREATE TABLE user_keys (
            id                    BIGSERIAL PRIMARY KEY,
            user_id               BIGINT NOT NULL UNIQUE,
            encrypted_private_key TEXT NOT NULL,
            nonce                 TEXT NOT NULL
        );
    """
    url = f"{supabase_url or SUPABASE_URL}/rest/v1/user_keys"
    key = supabase_key or SUPABASE_SERVICE_KEY

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={
                "user_id": user_id,
                "encrypted_private_key": encrypted_private_key,
                "nonce": nonce
            },
            headers=headers
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Supabase insert failed [{response.status_code}]: {response.text}"
            )

async def delete_user_keys_from_supabase(
    user_id: int,
    supabase_url: str = None,
    supabase_key: str = None
):
    """
    Deletes the encrypted private key and nonce from the Supabase `user_keys` table
    via Supabase's PostgREST HTTP API when a user is completely deleted.
    """
    url = f"{supabase_url or SUPABASE_URL}/rest/v1/user_keys?user_id=eq.{user_id}"
    key = supabase_key or SUPABASE_SERVICE_KEY

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            url,
            headers=headers
        )
        if response.status_code not in (200, 204):
            raise RuntimeError(
                f"Supabase delete failed [{response.status_code}]: {response.text}"
            )


async def update_user_keys_in_supabase(
    user_id: int,
    encrypted_private_key: str,
    nonce: str,
    supabase_url: str = None,
    supabase_key: str = None
):
    """
    Replaces the encrypted private key and nonce for a given user_id
    in the Supabase `user_keys` table via a PATCH request.
    Used during password reset to re-encrypt with the new master key.
    """
    url = f"{supabase_url or SUPABASE_URL}/rest/v1/user_keys?user_id=eq.{user_id}"
    key = supabase_key or SUPABASE_SERVICE_KEY

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            url,
            json={
                "encrypted_private_key": encrypted_private_key,
                "nonce": nonce
            },
            headers=headers
        )
        if response.status_code not in (200, 204):
            raise RuntimeError(
                f"Supabase update failed [{response.status_code}]: {response.text}"
            )


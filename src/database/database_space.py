import os
import httpx

# === Supabase REST API Configuration ===
# Works on both local uvicorn AND Cloudflare Workers (pure HTTP, no C-extensions)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wufbwretjlxjinqghwbl.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind1ZmJ3cmV0amx4amlucWdod2JsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI4NTIyOTgsImV4cCI6MjA4ODQyODI5OH0.JfU5vYSeNKbo_9X6qS1ZgnBw0eVQhYZBoFV6_F0c3Bc"
)


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

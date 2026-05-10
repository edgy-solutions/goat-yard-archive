import os
import logging
import jwt
from jwt import PyJWKClient
from typing import Optional
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

CLERK_ISSUER = os.getenv("CLERK_ISSUER")  # e.g. https://clerk.your-app.com
if not CLERK_ISSUER:
    logging.warning("CLERK_ISSUER not set. JWT verification will fail.")

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Validates the Bearer token against Clerk JWKS.
    Returns the user_id (sub) if valid.
    Returns None if invalid (allows anonymous access handling by caller if strictly needed, 
    but Security(security) usually raises 403 on missing header. 
    User requirement: 'If invalid/missing, return None (do not raise 401)'.
    So checking usage...
    """
    token = credentials.credentials
    
    try:
        # Fetch JWKS
        jwks_url = f"{CLERK_ISSUER}/.well-known/jwks.json"
        jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        data = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=CLERK_ISSUER,
            options={"verify_aud": False} # key is usually enough for Clerk
        )
        return data.get("sub")
    except Exception as e:
        logging.error(f"JWT Verification Failed: {e}")
        return None

async def get_optional_user_id(credentials: Optional[HTTPAuthorizationCredentials] = Security(optional_security)):
    """
    Returns user_id if valid token provided, else None.
    Does not raise 401 if header missing.
    """
    if not credentials:
        return None
    return get_current_user_id(credentials)

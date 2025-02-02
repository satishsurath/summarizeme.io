# auth_utils.py
import os
import jwt
from jwt import PyJWKClient
from flask import request
import logging
from dotenv import load_dotenv
from db.models import User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text


logger = logging.getLogger(__name__)

# Load these from your .env file or other secure location
#Read the env file
load_dotenv()
CLOUDFLARE_JWKS_URL = os.getenv("CLOUDFLARE_JWKS_URL")
CLOUDFLARE_ISSUER = os.getenv("CLOUDFLARE_ISSUER")
CLOUDFLARE_AUD_TAG = os.getenv("CLOUDFLARE_AUD_TAG")

DB_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")
engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_user_email_dev_mode():
    """
    1) If dev mode (FLASK_ENV=development, or some other check),
       return a dummy email.
    2) Otherwise try reading the Cloudflare header or JWT.
    """

    # Example approach: check environment variable
    if os.getenv("FLASK_ENV") == "development":
        # Return a dummy user or None if you prefer
        return "dev@localhost"

    # Production/Cloudflare: Try the simple header first.
    #cf_email = request.headers.get('Cf-Access-Authenticated-User-Email')
    #if cf_email:
    #    return cf_email

    # If you want to do JWT validation:
    token = request.headers.get('Cf-Access-Jwt-Assertion') or request.cookies.get('CF_Authorization')
    if not token:
        return None  # not authenticated

    # Validate the JWT
    try:
        jwks_client = PyJWKClient(CLOUDFLARE_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLOUDFLARE_AUD_TAG,
            issuer=CLOUDFLARE_ISSUER
        )
        return payload.get("email")
    except jwt.exceptions.InvalidTokenError as e:
        logger.warning(f"Invalid CF Access token: {e}")
        return None
    

def get_current_user():
    """
    Returns a tuple: (email, role) or (None, None) if unauthenticated.
    """
    email = get_user_email_dev_mode()
    if not email:
        return None, None

    session = SessionLocal()
    try:
        user_obj = session.query(User).filter_by(email=email).first()
        if user_obj:
            return (user_obj.email, user_obj.role)
        else:
            # If you want to auto-provision a user with default=reader, do so:
            new_user = User(email=email, role="reader")
            session.add(new_user)
            session.commit()
            return (new_user.email, new_user.role)
    finally:
        session.close()
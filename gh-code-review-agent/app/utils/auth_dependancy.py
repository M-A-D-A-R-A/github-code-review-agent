import jwt
from fastapi import Depends
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer

from ..config import get_settings

security = HTTPBearer()
settings = get_settings()


class Auth:
    @staticmethod
    def decode_auth_token(auth_token):
        try:
            payload = jwt.decode(auth_token, settings.SECRET_KEY, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Signature expired")
        except jwt.InvalidTokenError:
            raise Exception("Invalid token")

    @staticmethod
    def get_logged_in_user(auth_token):
        resp = Auth.decode_auth_token(auth_token)
        identity = resp.get("claims", {}).get("identity", resp.get("identity"))
        system_identity = settings.SYSTEM_IDENTITY
        if not (identity == system_identity):
            raise Exception("Invalid identity")
        return True


async def token_required(auth: HTTPAuthorizationCredentials = Depends(security)):
    try:
        Auth.get_logged_in_user(auth.credentials)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.auth import (
    AuthenticatedSession,
    AuthenticationStoreError,
    InvalidSessionError,
    authenticate_session,
)


def _request_origin(request: Request) -> str:
    forwarded_protocol = request.headers.get("x-forwarded-proto")
    scheme = (
        forwarded_protocol.split(",", 1)[0].strip() if forwarded_protocol else request.url.scheme
    )
    return f"{scheme}://{request.headers['host']}"


def require_trusted_origin(request: Request) -> None:
    """Reject browser state-changing requests sent from another origin."""
    origin = request.headers.get("origin")
    if origin:
        parsed_origin = urlsplit(origin)
        normalized_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
        trusted_origins = {*settings.cors_origin_list, _request_origin(request)}
        if (
            not parsed_origin.scheme
            or not parsed_origin.netloc
            or parsed_origin.path
            or parsed_origin.query
            or parsed_origin.fragment
            or normalized_origin not in trusted_origins
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Untrusted request origin",
            )
        return

    # Non-browser clients often omit Origin. Modern browsers send Sec-Fetch-Site;
    # reject an explicitly cross-site request even when Origin is unavailable.
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Untrusted request origin",
        )


def get_current_session(request: Request) -> AuthenticatedSession:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        return authenticate_session(token)
    except InvalidSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from error
    except AuthenticationStoreError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from error

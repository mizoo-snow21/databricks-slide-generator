from __future__ import annotations

import logging
import os
from typing import Optional

from databricks.sdk import WorkspaceClient
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

_FORWARDED_TOKEN_HEADER = "X-Forwarded-Access-Token"
_APPS_RUNTIME_SIGNAL_ENV = "DATABRICKS_APP_NAME"


def _is_apps_runtime() -> bool:
    return bool(os.environ.get(_APPS_RUNTIME_SIGNAL_ENV))


def _build_user_client(token: str):
    host = os.environ.get("DATABRICKS_HOST")
    if not host:
        logger.warning("No DATABRICKS_HOST in env; cannot build user-token client")
        return None
    # auth_type="pat" alone is NOT enough: the SDK validates auth-method
    # uniqueness BEFORE filtering by auth_type, so it still detects the
    # CLIENT_ID / CLIENT_SECRET env vars that Databricks Apps injects for
    # the SP and raises "more than one authorization method configured".
    # Pass empty string for those two fields to explicitly override the
    # env-var-derived values and force PAT-only auth.
    return WorkspaceClient(
        host=host,
        token=token,
        auth_type="pat",
        client_id="",
        client_secret="",
    )


def build_default_workspace_client():
    """Local-dev only: default-config WorkspaceClient (env-var-based credentials)."""
    try:
        return WorkspaceClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Default WorkspaceClient unavailable: %s", exc)
        return None


def get_sp_workspace_client():
    """FastAPI dependency: SP-authenticated WorkspaceClient for read-only
    metadata operations that user OBO cannot authorize (e.g. Lakeview reads
    when the workspace doesn't grant the 'dashboards' OAuth scope to apps).

    Returns None only when the SDK cannot construct a client at all."""
    return build_default_workspace_client()


def get_user_workspace_client(
    x_forwarded_access_token: Optional[str] = Header(
        default=None,
        alias=_FORWARDED_TOKEN_HEADER,
    ),
):
    """FastAPI dependency. Returns a WorkspaceClient using the requesting
    user's OAuth token (Databricks Apps OBO). In local dev, falls back to
    default-config (env vars). Inside Apps runtime, raises HTTPException(503)
    if the forwarded token is missing — never silently uses SP for an
    interactive request."""
    if x_forwarded_access_token and x_forwarded_access_token.strip():
        token = x_forwarded_access_token.strip()
        client = _build_user_client(token)
        if client is not None:
            return client
        if _is_apps_runtime():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "OBO user-token client construction failed: DATABRICKS_HOST "
                    "not set in app environment"
                ),
            )
        return None

    if _is_apps_runtime():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "On-behalf-of-user authentication is not configured. "
                "Ensure 'user_authorization.scopes' is set in app.yaml and the "
                "user has consented to the requested scopes."
            ),
        )
    return build_default_workspace_client()

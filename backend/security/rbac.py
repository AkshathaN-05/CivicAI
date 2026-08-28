"""RBAC — Role-based access control dependency — Part A §13, §19, T3-1.

Usage in route handlers:

    from security.rbac import require_role

    @router.post("/admin/action")
    async def admin_action(
        _user: dict = Depends(require_role("admin")),
    ):
        # _user is the verified current_user dict
        ...

Raises:
    HTTPException 403 — authenticated user does not have the required role.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status


def require_role(required_role: str):
    """Return a FastAPI dependency that enforces *required_role*.

    Wraps ``get_current_user`` so the route both authenticates the request
    (401 on bad JWT) and authorizes it (403 on wrong role) in one dependency.

    Args:
        required_role: One of 'citizen', 'admin', 'authority_officer'
                       (mirrors the user_role PostgreSQL enum, Part A §7).

    Returns:
        A FastAPI dependency callable that yields the verified current_user
        dict so downstream code can also read user identity from it.
    """
    # Import here to avoid circular dependency at module load time.
    from dependencies import get_current_user

    async def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        user_role = current_user.get("app_role", "citizen")
        if user_role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Requires role '{required_role}'; "
                    f"current role is '{user_role}'."
                ),
            )
        return current_user

    return _dependency

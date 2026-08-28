"""IDOR ownership check — Part A §13, §19, T3-1.

Usage in service layer:

    from security.ownership import verify_ownership

    verify_ownership(complaint.user_id, current_user["sub"])

Raises:
    HTTPException 403 — requesting user does not own the entity.
"""
from __future__ import annotations

from fastapi import HTTPException, status


def verify_ownership(entity_user_id: str, current_user_id: str) -> None:
    """Raise 403 if *current_user_id* does not own the entity.

    Admins bypass this check at the service layer by not calling this
    function when ``is_admin`` is True (Part A §19).

    Args:
        entity_user_id:  The ``user_id`` stored on the DB entity.
        current_user_id: The ``sub`` claim from the verified JWT.

    Raises:
        HTTPException 403: caller does not own the entity.
    """
    if entity_user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not own this resource.",
        )

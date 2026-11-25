"""
Centralized Authorization and Case Isolation Layer.

Enforces:
- Role-based access control (ADMIN, SUPERVISOR, INVESTIGATOR, ANALYST)
- Organization-level isolation when organization_id is assigned
- Case-level membership verification
- Canonical case identifier mapping (UUID <-> case_code <-> external_case_ref)
- Strict evidence-to-case ownership verification
- Strict cross-case intelligence authorization (all involved cases must be authorized)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem
from app.models.user import User


@dataclass(frozen=True)
class AuthorizedScope:
    user_id: str
    role: str
    organization_id: Optional[str]
    is_global_admin: bool
    allowed_case_ids: Optional[Set[str]] = None
    allowed_case_codes: Optional[Set[str]] = None
    allowed_canonical_refs: Optional[Set[str]] = None
    case_id_to_code: dict[str, str] = field(default_factory=dict)
    code_to_case_id: dict[str, str] = field(default_factory=dict)

    @property
    def is_unrestricted(self) -> bool:
        return self.allowed_canonical_refs is None

    def contains_case(self, identifier: str) -> bool:
        if self.allowed_canonical_refs is None:
            return True
        return str(identifier) in self.allowed_canonical_refs


def _parse_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def resolve_case_by_identifier(identifier: str, db: Session) -> Optional[Case]:
    """
    Resolve a case using canonical UUID, case_code, or external_case_ref.
    Never throws on non-UUID strings.
    """
    if not identifier:
        return None
    parsed = _parse_uuid(identifier)
    if parsed is not None:
        case = db.query(Case).filter(Case.id == parsed).first()
        if case:
            return case
    return db.query(Case).filter(
        or_(Case.case_code == identifier, Case.external_case_ref == identifier)
    ).first()


def _same_organization(user: User, case: Case) -> bool:
    """
    Organization isolation:
    - ADMIN is global across organizations.
    - If user has an organization_id, case must belong to that same organization
      (unless case has no organization assigned yet for legacy compatibility).
    """
    if user.role == "ADMIN":
        return True
    user_org = getattr(user, "organization_id", None)
    case_org = getattr(case, "organization_id", None)
    if user_org is not None and case_org is not None:
        return str(user_org) == str(case_org)
    if user_org is not None and case_org is None:
        return False
    return True


def require_case_access(
    case_identifier: str,
    current_user: User,
    db: Session,
    required_case_roles: Optional[Iterable[str]] = None,
) -> Case:
    """
    Verify that the case exists and that current_user is authorized to access it.
    Raises HTTP 404 if case does not exist, HTTP 403 if unauthorized.
    """
    case = resolve_case_by_identifier(case_identifier, db)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    if not _same_organization(current_user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: case belongs to another organization",
        )

    if current_user.role == "ADMIN":
        return case

    if current_user.role == "SUPERVISOR":
        # Supervisor has access to all cases within their organization
        return case

    member = db.query(CaseMember).filter(
        CaseMember.case_id == case.id,
        CaseMember.user_id == current_user.id,
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this case",
        )

    if required_case_roles is not None:
        allowed_roles = {r.upper() for r in required_case_roles}
        if (member.case_role or "").upper() not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient case role permissions for this operation",
            )

    return case


def require_evidence_access(
    case_identifier: str,
    evidence_id: str,
    current_user: User,
    db: Session,
    required_case_roles: Optional[Iterable[str]] = None,
) -> Tuple[Case, EvidenceItem]:
    """
    Verify both case access AND that the evidence item explicitly belongs to that case.
    Prevents cross-case IDOR when an authorized Case A user probes a Case B evidence_id.
    """
    case = require_case_access(case_identifier, current_user, db, required_case_roles=required_case_roles)

    ev_uuid = _parse_uuid(evidence_id)
    if ev_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    ev = db.query(EvidenceItem).filter(
        EvidenceItem.id == ev_uuid,
        EvidenceItem.case_id == case.id,
    ).first()
    if not ev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found in this case",
        )

    return case, ev


def get_authorized_case_scope(current_user: User, db: Session) -> AuthorizedScope:
    """
    Build the canonical authorized case scope for intelligence, graph, and search queries.
    - ADMIN: unrestricted (allowed_canonical_refs=None)
    - SUPERVISOR without organization_id: unrestricted (legacy compatibility)
    - SUPERVISOR with organization_id: all cases in their organization
    - INVESTIGATOR / ANALYST: only cases with active CaseMember membership in their organization
    """
    user_org = getattr(current_user, "organization_id", None)
    user_org_str = str(user_org) if user_org is not None else None

    if current_user.role == "ADMIN" or (current_user.role == "SUPERVISOR" and user_org is None):
        return AuthorizedScope(
            user_id=str(current_user.id),
            role=current_user.role,
            organization_id=user_org_str,
            is_global_admin=True,
            allowed_case_ids=None,
            allowed_case_codes=None,
            allowed_canonical_refs=None,
        )

    if current_user.role == "SUPERVISOR" and user_org is not None:
        cases = db.query(Case).filter(Case.organization_id == user_org).all()
    else:
        q = (
            db.query(Case)
            .join(CaseMember, CaseMember.case_id == Case.id)
            .filter(CaseMember.user_id == current_user.id)
        )
        if user_org is not None:
            q = q.filter(Case.organization_id == user_org)
        cases = q.all()

    case_ids: Set[str] = set()
    case_codes: Set[str] = set()
    canonical_refs: Set[str] = set()
    id_to_code: dict[str, str] = {}
    code_to_id: dict[str, str] = {}

    for c in cases:
        cid_str = str(c.id)
        case_ids.add(cid_str)
        canonical_refs.add(cid_str)
        if c.case_code:
            case_codes.add(c.case_code)
            canonical_refs.add(c.case_code)
            id_to_code[cid_str] = c.case_code
            code_to_id[c.case_code] = cid_str
        ext_ref = getattr(c, "external_case_ref", None)
        if ext_ref:
            canonical_refs.add(ext_ref)
            code_to_id[ext_ref] = cid_str

    return AuthorizedScope(
        user_id=str(current_user.id),
        role=current_user.role,
        organization_id=user_org_str,
        is_global_admin=False,
        allowed_case_ids=case_ids,
        allowed_case_codes=case_codes,
        allowed_canonical_refs=canonical_refs,
        case_id_to_code=id_to_code,
        code_to_case_id=code_to_id,
    )


def all_cases_authorized(
    case_refs: Iterable[str],
    allowed_cases: Optional[Set[str]],
) -> bool:
    """
    Strict cross-case policy (PRD 8.2):
    Returns True ONLY if allowed_cases is None (global clearance) OR
    every non-empty case identifier in case_refs is present in allowed_cases.
    """
    if allowed_cases is None:
        return True
    cleaned = {str(c).strip() for c in case_refs if c and str(c).strip() and str(c).strip() != "Unavailable"}
    if not cleaned:
        return False
    return cleaned.issubset(allowed_cases)

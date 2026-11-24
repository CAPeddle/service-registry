"""Service management API: annotations keyed by identity.

A registration names a service; it is matched against the live inventory and
recorded as that identity's annotation. Edits from the landing page address an
annotation by its identity key directly. Identity keys contain ':' and '/', so
they travel in the JSON body or the query string, never in a path segment.

Page edits win: a registration does not overwrite a description or health path
set from the page. When it carries a different value for one, the registration
is held in ``registration_attempts`` for review on the landing page.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from src.api.dependencies.services import get_inventory_service
from src.api.schemas.service_schema import AnnotationResponse, AnnotationUpdate, ServiceCreate
from src.models.annotation import Annotation
from src.models.base import get_db
from src.models.registration_attempt import PROTECTED_FIELDS, RegistrationAttempt
from src.repositories.annotation_repository import AnnotationRepository
from src.repositories.registration_attempt_repository import RegistrationAttemptRepository
from src.services.discovery.inventory import InventoryRow, InventoryService, parse_identity_key

router = APIRouter()


@router.get("", response_model=List[AnnotationResponse])
def list_annotations(db: Session = Depends(get_db)) -> List[Annotation]:
    """List every annotation."""
    return AnnotationRepository(db).list()


@router.post("", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
def register_service(
    service_data: ServiceCreate,
    db: Session = Depends(get_db),
    inventory: InventoryService = Depends(get_inventory_service),
) -> Annotation:
    """Record a registration as an annotation.

    A name matching a discovered service annotates that service with the
    description and health path. Its base_url is not stored: registrations
    typically send a loopback or old-host URL, and the page builds links from
    the visitor's address. A name matching nothing becomes ``manual:<name>``,
    whose only link is the base_url.

    A description or health path set from the page is kept. If the
    registration carries a different value for it, the registration is held
    for review; the response is still the (unchanged) annotation.
    """
    repo = AnnotationRepository(db)
    name = service_data.name
    key = _match_inventory(inventory.get().rows, name) or _match_annotation(repo, name)
    if key is None:
        key = f"manual:{name}"
    current = repo.get(key)
    fields, held = {}, []
    for field, source in PROTECTED_FIELDS.items():
        value = getattr(service_data, source)
        if current is None or not getattr(current, f"{field}_from_page"):
            fields[field] = value
        elif value is not None and value != getattr(current, field):
            held.append(field)
    if key.startswith("manual:"):
        fields["link_override"] = service_data.base_url
    attempts = RegistrationAttemptRepository(db)
    if held:
        attempts.record(
            key,
            name=name,
            description=service_data.description,
            base_url=service_data.base_url,
            health_endpoint=service_data.health_endpoint,
            held_fields=held,
        )
    else:
        attempts.delete_for(key)  # committed with the annotation below
    return repo.upsert(key, **fields)


@router.put("/annotation", response_model=AnnotationResponse)
def update_annotation(update: AnnotationUpdate, db: Session = Depends(get_db)) -> Annotation:
    """Create or change the annotation for one identity key; omitted fields are unchanged."""
    fields = update.model_dump(exclude_unset=True)
    key = fields.pop("identity_key")
    cleared = []
    for field in PROTECTED_FIELDS:
        if field in fields:
            fields[f"{field}_from_page"] = fields[field] is not None
            if fields[field] is None:
                cleared.append(field)
    if cleared:
        # A cleared field is no longer protected, so a held value for it is moot.
        RegistrationAttemptRepository(db).release(key, cleared)  # committed below
    return AnnotationRepository(db).upsert(key, **fields)


@router.delete("/annotation", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(
    identity_key: str = Query(..., min_length=1), db: Session = Depends(get_db)
) -> Response:
    """Remove the annotation for one identity key, and any registration held for it."""
    RegistrationAttemptRepository(db).delete_for(identity_key)  # committed with the deletion
    if not AnnotationRepository(db).delete(identity_key):
        raise HTTPException(status_code=404, detail="Annotation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/registrations/{attempt_id}/apply", response_model=AnnotationResponse)
def apply_registration(attempt_id: int, db: Session = Depends(get_db)) -> Annotation:
    """Use a held registration's values for its held fields; they stop being page-protected.

    A field whose page protection has since been cleared is left as it is.
    """
    attempts = RegistrationAttemptRepository(db)
    attempt = _attempt_or_404(attempts, attempt_id)
    annotations = AnnotationRepository(db)
    current = annotations.get(attempt.identity_key)
    if current is None:
        attempts.delete(attempt)
        raise HTTPException(status_code=404, detail="Annotation not found")
    fields = {}
    for field in attempt.held_fields:
        if getattr(current, f"{field}_from_page"):
            fields[field] = getattr(attempt, PROTECTED_FIELDS[field])
            fields[f"{field}_from_page"] = False
    attempts.delete(attempt, commit=False)  # committed with the annotation below
    return annotations.upsert(attempt.identity_key, **fields)


@router.delete("/registrations/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_registration(attempt_id: int, db: Session = Depends(get_db)) -> Response:
    """Discard a held registration without applying it."""
    attempts = RegistrationAttemptRepository(db)
    attempts.delete(_attempt_or_404(attempts, attempt_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _attempt_or_404(
    attempts: RegistrationAttemptRepository, attempt_id: int
) -> RegistrationAttempt:
    attempt = attempts.get(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Held registration not found")
    return attempt


def _names(row: InventoryRow) -> set[str]:
    """The names a registration may use for a discovered row."""
    parts = parse_identity_key(row.identity_key)
    if parts is None:
        return set()
    if parts.prefix in ("system", "user"):
        return {parts.name}
    if parts.prefix == "docker":
        return {parts.name, parts.name.rsplit("/", 1)[-1], *row.container_names}
    return set()


def _match_inventory(rows: List[InventoryRow], name: str) -> Optional[str]:
    return next((row.identity_key for row in rows if name in _names(row)), None)


def _match_annotation(repo: AnnotationRepository, name: str) -> Optional[str]:
    return next((a.identity_key for a in repo.list() if a.identity_key.endswith(f":{name}")), None)

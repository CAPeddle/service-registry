"""Data access for registrations held for review."""
from typing import Optional
from sqlalchemy.orm import Session
from src.models.registration_attempt import RegistrationAttempt


class RegistrationAttemptRepository:
    """Record, list, get and delete held registrations; one pending entry per identity key."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, attempt_id: int) -> Optional[RegistrationAttempt]:
        return self.session.get(RegistrationAttempt, attempt_id)

    def list(self) -> list[RegistrationAttempt]:
        return (
            self.session.query(RegistrationAttempt)
            .order_by(RegistrationAttempt.received_at.desc(), RegistrationAttempt.id.desc())
            .all()
        )

    def record(self, identity_key: str, **fields) -> RegistrationAttempt:
        """Store a held registration, replacing any earlier one for the same identity key."""
        self.session.query(RegistrationAttempt).filter_by(identity_key=identity_key).delete()
        attempt = RegistrationAttempt(identity_key=identity_key, **fields)
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return attempt

    def delete(self, attempt: RegistrationAttempt, *, commit: bool = True) -> None:
        self.session.delete(attempt)
        if commit:
            self.session.commit()

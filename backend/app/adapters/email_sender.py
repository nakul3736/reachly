"""Outbound email.

Deliberately unimplemented. Per ADR 0004 Reachly does not send email — it drafts,
and the student sends from their own address. Verification and password reset are
the only legitimate transactional cases, and both are out of scope for feature 01.

This protocol exists so adding them later is a new implementation rather than a
change to every call site. `NoopSender` is the only implementation, and it records
nothing and sends nothing.
"""

from typing import Protocol


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class NoopSender:
    """Accepts and discards. The honest implementation of a feature we do not have."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        return None

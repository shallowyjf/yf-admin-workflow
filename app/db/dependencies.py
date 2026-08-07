"""Request-scoped database dependencies."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db_session(request: Request) -> Iterator[Session]:
    with request.app.state.database.session_factory() as session:
        yield session

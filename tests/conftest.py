from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.data_permission.models  # noqa: F401
import app.iam.models  # noqa: F401
import app.project.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.main import create_app


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        app_name="权限流程测试平台",
        environment="test",
        database_url="sqlite://",
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Iterator[Session]:
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)
    try:
        with database.session_factory() as session:
            yield session
    finally:
        Base.metadata.drop_all(database.engine)
        database.dispose()

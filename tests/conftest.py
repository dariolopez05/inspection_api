import io
from collections.abc import AsyncIterator, Iterator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401  registra modelos en Base.metadata
from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.main import app


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def api_key() -> str:
    return get_settings().api_key


@pytest.fixture
def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest_asyncio.fixture
async def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.model = object()
    app.state.s3 = MagicMock()
    app.state.s3_bucket = "test-bucket"
    monkeypatch.setattr(
        "app.api.routers.inspect.predict", lambda model, tensor: (True, 0.9876)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

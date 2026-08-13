"""Seed the independent platform root account for local demonstration."""

from app.db.session import Database

from .models import PlatformUser
from .repository import AuthRepository
from .security import PasswordHasher

PLATFORM_ROOT_USERNAME = "root"
PLATFORM_ROOT_PASSWORD = "Root@123456"


def seed_platform_root(repository: AuthRepository) -> PlatformUser:
    user = repository.get_platform_user(PLATFORM_ROOT_USERNAME)
    if user is None:
        user = PlatformUser(
            username=PLATFORM_ROOT_USERNAME,
            display_name="平台 Root 管理员",
            password_hash=PasswordHasher().hash(PLATFORM_ROOT_PASSWORD),
        )
        repository.save(user)
        repository.refresh(user)
    return user


def main() -> None:
    from app.core.config import get_settings

    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            user = seed_platform_root(AuthRepository(session))
        print(f"Platform root ready: {user.username}")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()

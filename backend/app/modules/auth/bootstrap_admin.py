import asyncio
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.database import (
    check_database,
    create_mongo_client,
    initialize_persistence,
)
from app.modules.auth.documents import UserDocument
from app.modules.auth.passwords import hash_password


async def bootstrap_admin() -> int:
    settings = get_settings()
    if not settings.BOOTSTRAP_ADMIN_EMAIL or not settings.BOOTSTRAP_ADMIN_PASSWORD:
        print("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in .env.")
        return 2

    password = settings.BOOTSTRAP_ADMIN_PASSWORD.get_secret_value()
    if len(password) < 12:
        print("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.")
        return 2

    try:
        email = str(TypeAdapter(EmailStr).validate_python(settings.BOOTSTRAP_ADMIN_EMAIL))
    except ValidationError:
        print("BOOTSTRAP_ADMIN_EMAIL must be a valid email address.")
        return 2

    client = create_mongo_client(settings)
    try:
        await check_database(client, settings.MONGODB_REPLICA_SET)
        database = client[settings.MONGODB_DATABASE]
        await initialize_persistence(database)

        if await UserDocument.find_all().count() > 0:
            print("Bootstrap skipped; the database already contains a user.")
            return 0

        administrator = UserDocument(
            normalized_email=email.casefold(),
            display_name="Administrator",
            password_hash=hash_password(password),
            role="admin",
        )
        try:
            await administrator.insert()
        except DuplicateKeyError:
            print("Bootstrap skipped; another administrator was created first.")
            return 0

        print("Initial administrator created. Remove bootstrap credentials from .env.")
        return 0
    finally:
        await client.close()


def main() -> None:
    try:
        exit_code = asyncio.run(bootstrap_admin())
    except KeyboardInterrupt:
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

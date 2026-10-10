import asyncio
import logging
import sys

from pymongo.errors import PyMongoError

from app.core.config import get_settings
from app.core.database import (
    check_database,
    create_mongo_client,
    initialize_persistence,
)
from app.modules.document.jobs import RenderWorker


LOGGER = logging.getLogger("scesi.worker")
POLL_SECONDS = 1.0


async def run_worker() -> None:
    settings = get_settings()
    client = create_mongo_client(settings)
    worker = RenderWorker(settings, client)
    try:
        await check_database(client, settings.MONGODB_REPLICA_SET)
        await initialize_persistence(client[settings.MONGODB_DATABASE])
        LOGGER.info("Document export worker started")
        while True:
            try:
                processed = await worker.run_once()
            except PyMongoError:
                LOGGER.warning("Document export worker database operation failed")
                processed = False
            if not processed:
                await asyncio.sleep(POLL_SECONDS)
    finally:
        await client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        LOGGER.info("Document export worker stopped")
        sys.exit(130)


if __name__ == "__main__":
    main()

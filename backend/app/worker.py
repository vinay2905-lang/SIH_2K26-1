"""Run the background worker: `python -m app.worker`."""
import logging

from .config import get_settings
from .db import init_db
from .jobs import work_forever


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    get_settings().check_production()
    init_db()
    logging.getLogger("pramaan.worker").info("worker started")
    work_forever()


if __name__ == "__main__":
    main()

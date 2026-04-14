from __future__ import annotations

from db import get_session
from init_db import init_db


def main() -> None:
    with get_session() as session:
        init_db(session)


if __name__ == "__main__":
    main()

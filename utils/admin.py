from config import ADMIN_IDS


ADMIN_ID_SET = set(ADMIN_IDS)


def is_admin(user_id: int | None) -> bool:
    return user_id in ADMIN_ID_SET

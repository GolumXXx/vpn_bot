def parse_admin_ids(raw_value: str | None) -> list[int]:
    if not raw_value:
        return []

    admin_ids: list[int] = []
    seen_ids: set[int] = set()

    for item in raw_value.split(","):
        item = item.strip()
        if not item.isdigit():
            continue

        admin_id = int(item)
        if admin_id in seen_ids:
            continue

        seen_ids.add(admin_id)
        admin_ids.append(admin_id)

    return admin_ids

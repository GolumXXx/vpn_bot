def parse_callback(data: str | None) -> tuple[str, ...]:
    if not data:
        return ()

    return tuple(part.strip() for part in str(data).split(":"))


def parse_callback_int(data: str | None, prefix: str | None = None) -> int | None:
    if not data:
        return None

    value = str(data)
    if prefix:
        if not value.startswith(prefix):
            return None
        value = value[len(prefix):]
    else:
        parts = parse_callback(value)
        if len(parts) < 2:
            return None
        value = parts[1]

    try:
        return int(value)
    except (TypeError, ValueError):
        return None

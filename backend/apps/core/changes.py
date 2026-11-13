from typing import Any


def apply_changes(obj: Any, data: dict, fields: tuple[str, ...]) -> dict:
    """Set the listed fields from ``data`` and return ``{field: [old, new]}`` for real changes."""
    changes = {}
    for name in fields:
        if name in data and getattr(obj, name) != data[name]:
            changes[name] = [getattr(obj, name), data[name]]
            setattr(obj, name, data[name])
    return changes

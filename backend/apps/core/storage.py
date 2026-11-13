"""File storage behind a small interface so S3 or MinIO can replace it later (not built now).

Keys are generated here (``yyyy/mm/<uuid>``); user-supplied names never reach the filesystem.
"""

import os
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

KEY_RE = re.compile(r"^\d{4}/\d{2}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class InvalidKey(ValueError):
    pass


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not KEY_RE.match(key):
            raise InvalidKey("invalid storage key")
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise InvalidKey("storage key escapes the media root")
        return path

    def save(self, data: bytes) -> str:
        now = timezone.now()
        key = f"{now:%Y}/{now:%m}/{uuid.uuid4()}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o755)  # noqa: S103  # nosec B103  nginx (another uid) must traverse; the volume is private
        tmp = path.with_name(path.name + ".part")
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)  # atomic: readers never see a partial file
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(settings.MEDIA_ROOT)

"""Full backup of one installation into one encrypted file, and restore into an empty installation.

A backup holds every row (copied table by table in one consistent snapshot), every stored file and the key that
protects two-step sign-in secrets. It is encrypted with a passphrase: scrypt for the key, AES-256-GCM in 1 MB
chunks. Each chunk is authenticated with its number and whether it is the last, so a changed, reordered or
shortened file is refused.

Restore loads the rows into a database that already has the same schema, in one transaction: it either happens
completely or not at all. It needs the database administrator (`restore_agent` runs it), because the audit log
and notes are protected against rewriting for the application's own role.
"""

import io
import json
import os
import shutil
import struct
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.core.storage import KEY_RE

MAGIC = b"RSBK1\n"
CHUNK = 1024 * 1024
FORMAT = 1
SKIP_DATA = {"django_session"}  # signed-in sessions are not carried over
NEVER_TOUCH = {"django_migrations"}  # the schema history belongs to the installation
MIN_PASSPHRASE = 12


class BackupError(Exception):
    """The message is shown to the user as written."""


# encryption


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def _nonce(prefix: bytes, number: int) -> bytes:
    return prefix + struct.pack(">I", number)


def encrypt_file(source: Path, target, passphrase: str) -> None:
    salt, prefix = os.urandom(16), os.urandom(8)
    cipher = AESGCM(_key(passphrase, salt))
    target.write(MAGIC + salt + prefix)
    with open(source, "rb") as handle:
        block, number = handle.read(CHUNK), 0
        while True:
            following = handle.read(CHUNK)
            last = b"\x01" if not following else b"\x00"
            sealed = cipher.encrypt(_nonce(prefix, number), block, last)
            target.write(last + struct.pack(">I", len(sealed)) + sealed)
            if not following:
                return
            block, number = following, number + 1


def decrypt_file(source, target, passphrase: str) -> None:
    head = source.read(len(MAGIC) + 24)
    if len(head) != len(MAGIC) + 24 or not head.startswith(MAGIC):
        raise BackupError("This is not a RedShadow backup file.")
    salt, prefix = head[len(MAGIC) : len(MAGIC) + 16], head[len(MAGIC) + 16 :]
    cipher = AESGCM(_key(passphrase, salt))
    number = 0
    while True:
        frame = source.read(5)
        if len(frame) != 5:
            raise BackupError("The backup file is incomplete.")
        last, size = frame[:1], struct.unpack(">I", frame[1:])[0]
        if size > CHUNK + 16:
            raise BackupError("The backup file is damaged.")
        sealed = source.read(size)
        try:
            target.write(cipher.decrypt(_nonce(prefix, number), sealed, last))
        except (InvalidTag, ValueError):
            raise BackupError("Wrong passphrase, or the file was changed.") from None
        if last == b"\x01":
            if source.read(1):
                raise BackupError("The backup file is damaged.")
            return
        number += 1


# database


def _tables(cursor) -> list[str]:
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    return [row[0] for row in cursor.fetchall() if row[0] not in NEVER_TOUCH]


def _columns(cursor, table: str) -> list[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s "
        "AND is_generated = 'NEVER' ORDER BY ordinal_position",
        [table],
    )
    return [row[0] for row in cursor.fetchall()]


def _migrations(cursor) -> list[str]:
    cursor.execute("SELECT app || '.' || name FROM django_migrations ORDER BY 1")
    return [row[0] for row in cursor.fetchall()]


def _quoted(names: list[str]) -> str:
    return ", ".join(connection.ops.quote_name(n) for n in names)


def staging_dir() -> Path:
    path = Path(settings.BACKUP_STAGING_DIR)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _add(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


def write_bundle(passphrase: str, target) -> dict:
    """Write the encrypted backup of this installation to ``target``. Returns the manifest."""
    work = Path(tempfile.mkdtemp(prefix="backup-", dir=staging_dir()))
    try:
        plain = work / "bundle.tar"
        outermost = not connection.in_atomic_block
        with transaction.atomic(), connection.cursor() as cursor, tarfile.open(plain, "w") as archive:
            if outermost:  # one snapshot for every table
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            tables = {}
            for table in _tables(cursor):
                columns = _columns(cursor, table)
                tables[table] = columns
                if table in SKIP_DATA:
                    continue
                dump = work / "table.copy"
                query = f"COPY (SELECT {_quoted(columns)} FROM {connection.ops.quote_name(table)}) TO STDOUT"  # noqa: S608 - names from the catalogue, quoted
                with open(dump, "wb") as out, cursor.cursor.copy(query) as copy:
                    for block in copy:
                        out.write(block)
                archive.add(dump, arcname=f"db/{table}", recursive=False)
            files = 0
            media = Path(settings.MEDIA_ROOT)
            for path in sorted(media.rglob("*")) if media.exists() else []:
                key = path.relative_to(media).as_posix()
                if path.is_file() and not path.is_symlink() and KEY_RE.match(key):
                    archive.add(path, arcname=f"media/{key}", recursive=False)
                    files += 1
            manifest = {
                "format": FORMAT,
                "version": settings.APP_VERSION,
                "created_at": timezone.now().isoformat(),
                "migrations": _migrations(cursor),
                "tables": tables,
                "files": files,
            }
            _add(archive, "manifest.json", json.dumps(manifest).encode())
            _add(archive, "mfa_key", settings.MFA_ENCRYPTION_KEY.encode())
        encrypt_file(plain, target, passphrase)
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def unpack(source, passphrase: str, destination: Path) -> dict:
    """Decrypt and unpack into ``destination``. Only the expected names are written. Returns the manifest."""
    plain = destination / "bundle.tar"
    with open(plain, "wb") as out:
        decrypt_file(source, out, passphrase)
    try:
        with tarfile.open(plain, "r:") as archive:
            for member in archive:
                parts = PurePosixPath(member.name).parts
                allowed = member.name in ("manifest.json", "mfa_key") or (
                    (len(parts) == 2 and parts[0] == "db" and parts[1].replace("_", "").isalnum())
                    or (parts[:1] == ("media",) and KEY_RE.match("/".join(parts[1:])))
                )
                if not member.isfile() or not allowed:
                    raise BackupError("The backup holds an entry that does not belong in it.")
                path = destination.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as data, open(path, "wb") as out:
                    shutil.copyfileobj(data, out)
        manifest = json.loads((destination / "manifest.json").read_text())
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise BackupError("The backup file is damaged.") from exc
    finally:
        plain.unlink(missing_ok=True)
    if manifest.get("format") != FORMAT:
        raise BackupError("This backup was made in a format this version cannot read.")
    return manifest


def check_compatible(manifest: dict) -> None:
    with connection.cursor() as cursor:
        same = manifest.get("migrations") == _migrations(cursor)
    if not same:
        raise BackupError(
            f"The backup was made by RedShadow {manifest.get('version', '?')}, whose database layout differs from "
            f"this one ({settings.APP_VERSION}). Install that version, restore, then upgrade."
        )


def is_empty() -> bool:
    """True while nothing has been recorded that a restore would overwrite."""
    from apps.engagements.models import Engagement
    from apps.findings.models import Finding
    from apps.organisations.models import Organisation

    return not (
        Organisation.objects.exists() or Engagement.all_objects.exists() or Finding._base_manager.all().exists()
    )


def load(source_dir: Path, manifest: dict) -> None:
    """Replace the contents of this empty installation with the unpacked backup. Needs the database admin."""
    if not is_empty():
        raise BackupError("This installation already holds data, so nothing was restored.")
    check_compatible(manifest)
    try:
        old_key = Fernet((source_dir / "mfa_key").read_bytes())
    except (OSError, ValueError) as exc:
        raise BackupError("The backup file is damaged.") from exc

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        # No triggers or foreign key checks while loading rows that were consistent when they were copied.
        cursor.execute("SET LOCAL session_replication_role = replica")
        tables = _tables(cursor)
        if sorted(manifest["tables"]) != tables:
            raise BackupError("The backup does not list the same tables as this installation.")
        cursor.execute(f"TRUNCATE {_quoted(tables)} CASCADE")
        for table in tables:
            dump = source_dir / "db" / table
            if table in SKIP_DATA:
                continue
            columns = manifest["tables"][table]
            if sorted(columns) != sorted(_columns(cursor, table)) or not dump.is_file():
                raise BackupError(f"The backup does not match the table {table}.")
            query = f"COPY {connection.ops.quote_name(table)} ({_quoted(columns)}) FROM STDIN"
            with open(dump, "rb") as data, cursor.cursor.copy(query) as copy:
                while block := data.read(CHUNK):
                    copy.write(block)
        _reset_sequences(cursor)
        _rekey_mfa(cursor, old_key)
        cursor.execute("SET LOCAL session_replication_role = origin")
        _restore_media(source_dir / "media")


def _reset_sequences(cursor) -> None:
    cursor.execute(
        "SELECT s.relname, t.relname, a.attname FROM pg_class s "
        "JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i') "
        "JOIN pg_class t ON t.oid = d.refobjid "
        "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid "
        "JOIN pg_namespace n ON n.oid = s.relnamespace "
        "WHERE s.relkind = 'S' AND n.nspname = 'public'"
    )
    for sequence, table, column in cursor.fetchall():
        name, col = connection.ops.quote_name(table), connection.ops.quote_name(column)
        cursor.execute(
            f"SELECT setval(%s::regclass, COALESCE((SELECT max({col}) FROM {name}), 0) + 1, false)",  # noqa: S608 - names from the catalogue, quoted
            [connection.ops.quote_name(sequence)],
        )


def _rekey_mfa(cursor, old_key: Fernet) -> None:
    """Two-step secrets were sealed with the old installation's key; seal them with this one."""
    new_key = Fernet(settings.MFA_ENCRYPTION_KEY.encode())
    cursor.execute("SELECT id, mfa_secret_enc FROM accounts_user WHERE mfa_secret_enc <> ''")
    for pk, sealed in cursor.fetchall():
        try:
            value = new_key.encrypt(old_key.decrypt(sealed.encode())).decode()
        except InvalidToken:
            raise BackupError("A two-step sign-in secret in the backup cannot be read.") from None
        cursor.execute("UPDATE accounts_user SET mfa_secret_enc = %s WHERE id = %s", [value, pk])


def _restore_media(source: Path) -> None:
    media = Path(settings.MEDIA_ROOT)
    for path in source.rglob("*") if source.exists() else []:
        if path.is_file():
            target = media / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            target.chmod(0o644)  # nginx, another user, serves the file after Django has authorised it

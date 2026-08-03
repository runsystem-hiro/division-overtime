from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .database import Database


class KotSyncDivisionError(RuntimeError):
    pass


class KotSyncDivisionConflictError(KotSyncDivisionError):
    pass


class KotSyncDivisionNotFoundError(KotSyncDivisionError):
    pass


@dataclass(frozen=True, slots=True)
class KotSyncDivision:
    division_code: str
    is_enabled: bool
    created_at: str
    updated_at: str


class KotSyncDivisionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def normalize_code(value: str) -> str:
        code = value.strip()
        if not code:
            raise KotSyncDivisionError("Division code must not be empty")
        if len(code) > 64:
            raise KotSyncDivisionError("Division code must be 64 characters or fewer")
        if not code.isdigit():
            raise KotSyncDivisionError("Division code must contain digits only")
        return code

    def seed_if_empty(self, division_codes: tuple[str, ...]) -> None:
        normalized = tuple(dict.fromkeys(self.normalize_code(code) for code in division_codes))
        if not normalized:
            raise KotSyncDivisionError("At least one KOT sync division code is required")
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as conn:
            count = int(conn.execute("SELECT COUNT(*) FROM kot_sync_divisions").fetchone()[0])
            if count:
                return
            conn.executemany(
                "INSERT INTO kot_sync_divisions(division_code, is_enabled, created_at, updated_at) "
                "VALUES(?, 1, ?, ?)",
                ((code, now, now) for code in normalized),
            )

    def list_all(self) -> list[KotSyncDivision]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT division_code, is_enabled, created_at, updated_at "
                "FROM kot_sync_divisions ORDER BY division_code"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_enabled_codes(self) -> tuple[str, ...]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT division_code FROM kot_sync_divisions "
                "WHERE is_enabled = 1 ORDER BY division_code"
            ).fetchall()
        codes = tuple(str(row["division_code"]) for row in rows)
        if not codes:
            raise KotSyncDivisionError("At least one enabled KOT sync division is required")
        return codes

    def create(self, division_code: str) -> KotSyncDivision:
        code = self.normalize_code(division_code)
        now = datetime.now(UTC).isoformat()
        try:
            with self.database.transaction() as conn:
                conn.execute(
                    (
                        "INSERT INTO kot_sync_divisions"
                        "(division_code, is_enabled, created_at, updated_at) "
                        "VALUES(?, 1, ?, ?)"
                    ),
                    (code, now, now),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise KotSyncDivisionConflictError(
                    f"Division code {code} is already registered"
                ) from exc
            raise
        return self.get(code)

    def set_enabled(self, division_code: str, is_enabled: bool) -> KotSyncDivision:
        code = self.normalize_code(division_code)
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as conn:
            if not is_enabled:
                enabled_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM kot_sync_divisions WHERE is_enabled = 1"
                    ).fetchone()[0]
                )
                current = conn.execute(
                    "SELECT is_enabled FROM kot_sync_divisions WHERE division_code = ?",
                    (code,),
                ).fetchone()
                if current is None:
                    raise KotSyncDivisionNotFoundError(f"Division code {code} is not registered")
                if bool(current["is_enabled"]) and enabled_count <= 1:
                    raise KotSyncDivisionError("At least one enabled KOT sync division is required")
            cursor = conn.execute(
                "UPDATE kot_sync_divisions SET is_enabled = ?, updated_at = ? "
                "WHERE division_code = ?",
                (int(is_enabled), now, code),
            )
            if cursor.rowcount == 0:
                raise KotSyncDivisionNotFoundError(f"Division code {code} is not registered")
        return self.get(code)

    def delete(self, division_code: str) -> KotSyncDivision:
        code = self.normalize_code(division_code)
        with self.database.transaction() as conn:
            row = conn.execute(
                "SELECT division_code, is_enabled, created_at, updated_at "
                "FROM kot_sync_divisions WHERE division_code = ?",
                (code,),
            ).fetchone()
            if row is None:
                raise KotSyncDivisionNotFoundError(f"Division code {code} is not registered")
            if bool(row["is_enabled"]):
                enabled_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM kot_sync_divisions WHERE is_enabled = 1"
                    ).fetchone()[0]
                )
                if enabled_count <= 1:
                    raise KotSyncDivisionError("At least one enabled KOT sync division is required")
            conn.execute("DELETE FROM kot_sync_divisions WHERE division_code = ?", (code,))
        return self._from_row(row)

    def get(self, division_code: str) -> KotSyncDivision:
        code = self.normalize_code(division_code)
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT division_code, is_enabled, created_at, updated_at "
                "FROM kot_sync_divisions WHERE division_code = ?",
                (code,),
            ).fetchone()
        if row is None:
            raise KotSyncDivisionNotFoundError(f"Division code {code} is not registered")
        return self._from_row(row)

    @staticmethod
    def _from_row(row) -> KotSyncDivision:
        return KotSyncDivision(
            division_code=str(row["division_code"]),
            is_enabled=bool(row["is_enabled"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

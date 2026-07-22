from __future__ import annotations

import time
from collections.abc import Iterable

import requests


class KingOfTimeError(RuntimeError):
    pass


class KingOfTimeClient:
    def __init__(
        self,
        base_url: str,
        endpoint: str,
        token: str,
        connect_timeout: float,
        read_timeout: float,
        retry_count: int,
        retry_backoff: float,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url
        self.endpoint = endpoint
        self.timeout = (connect_timeout, read_timeout)
        self.retry_count = retry_count
        self.retry_backoff = retry_backoff
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def fetch_division_month(self, year_month: str, division_code: str) -> dict[str, int]:
        url = f"{self.base_url}{self.endpoint}/{year_month}"
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                response = self.session.get(
                    url,
                    params={"division": division_code},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise KingOfTimeError("Unexpected King of Time response format")
                return self._normalize(payload)
            except (requests.RequestException, ValueError, KingOfTimeError) as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self.retry_backoff * attempt)
        raise KingOfTimeError(
            f"Failed to fetch {year_month} division={division_code}: {last_error}"
        )

    @staticmethod
    def _normalize(records: Iterable[object]) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in records:
            if not isinstance(item, dict):
                continue
            key = str(item.get("employeeKey", ""))
            if not key:
                continue
            overtime = int(item.get("overtime", 0) or 0)
            night = int(item.get("nightOvertime", 0) or 0)
            result[key] = overtime + night
        return result

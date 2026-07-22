from __future__ import annotations

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackDeliveryError(RuntimeError):
    pass


class SlackMessenger:
    def __init__(self, token: str, client: WebClient | None = None):
        self.client = client or WebClient(token=token)
        self._user_cache: dict[str, str] = {}

    def send_dm(self, email: str, message: str) -> str:
        try:
            user_id = self._user_cache.get(email)
            if not user_id:
                lookup = self.client.users_lookupByEmail(email=email)
                user_id = str(lookup["user"]["id"])
                self._user_cache[email] = user_id
            opened = self.client.conversations_open(users=user_id)
            channel_id = str(opened["channel"]["id"])
            sent = self.client.chat_postMessage(channel=channel_id, text=message)
            return str(sent.get("ts", ""))
        except (SlackApiError, KeyError, TypeError, ValueError) as exc:
            raise SlackDeliveryError(f"Slack DM failed for {email}: {exc}") from exc

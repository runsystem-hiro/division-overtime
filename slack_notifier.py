#!/usr/bin/env python3
import os
import time
import socket
import logging
import hashlib
from datetime import datetime
from typing import Optional, List, Tuple
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackNotifier:
    RETRY_COUNT = 5
    RETRY_WAIT_SEC = 10
    BASE_DIR = Path(__file__).resolve().parent
    USER_ID_CACHE_DIR = BASE_DIR / "cache"

    def __init__(self, bot_token: str, user_email: Optional[str] = None):
        self.client = WebClient(token=bot_token)
        self.user_email: Optional[str] = user_email
        self.user_id: Optional[str] = self._load_or_fetch_user_id()

    def _get_cache_path(self) -> Optional[str]:
        if not self.user_email:
            return None
        os.makedirs(self.USER_ID_CACHE_DIR, exist_ok=True)
        # メールアドレスのハッシュでファイル名生成（安全かつ一意）
        email_hash = hashlib.sha256(self.user_email.encode()).hexdigest()
        return os.path.join(self.USER_ID_CACHE_DIR, f"user_id_{email_hash}.txt")

    def _load_or_fetch_user_id(self) -> Optional[str]:
        cache_path = self._get_cache_path()
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    user_id = f.read().strip()
                    if user_id:
                        logging.info(f"[Slack] キャッシュからユーザーIDを読み込み: {user_id}")
                        return user_id
            except Exception as e:
                logging.warning(f"[Slack] ユーザーIDキャッシュの読み込み失敗: {e}")

        # キャッシュがなければAPIから取得
        user_id = self._get_user_id()
        if user_id and cache_path:
            try:
                with open(cache_path, "w") as f:
                    f.write(user_id)
                logging.info(f"[Slack] ユーザーIDをキャッシュに保存: {user_id}")
            except Exception as e:
                logging.warning(f"[Slack] ユーザーIDキャッシュ保存失敗: {e}")
        return user_id

    def _get_user_id(self) -> Optional[str]:
        if not self.user_email:
            return None

        for attempt in range(self.RETRY_COUNT):
            try:
                response = self.client.users_lookupByEmail(
                    email=self.user_email)
                user = response.get("user") if response else None
                if user and "id" in user:
                    return user["id"]
                else:
                    logging.error(
                        f"[Slackエラー] ユーザーID取得失敗（{self.user_email}）: レスポンスに'user'または'id'がありません")
                    return None
            except SlackApiError as e:
                logging.error(
                    f"[Slackエラー] ユーザーID取得失敗（{self.user_email}）: {e.response['error']}")
                return None
            except socket.gaierror as e:
                logging.warning(
                    f"[ネットワークエラー] 名前解決失敗（{e}）: リトライ {attempt+1}/{self.RETRY_COUNT}")
                time.sleep(self.RETRY_WAIT_SEC)
            except Exception as e:
                logging.exception(f"[Slackエラー] 不明なエラー: {e}")
                return None

        logging.error(
            f"[Slackエラー] ユーザーID取得に{self.RETRY_COUNT}回失敗しました（{self.user_email}）")
        return None

    def _get_dm_channel_id(self) -> Optional[str]:
        if not self.user_id:
            logging.error("[Slackエラー] user_idがNoneのためDMチャンネルを開けません")
            return None
        try:
            conv = self.client.conversations_open(users=self.user_id)
            channel_info = conv.get("channel") if conv else None
            if channel_info and "id" in channel_info:
                return channel_info["id"]
            else:
                logging.error(
                    f"[Slackエラー] DMチャンネルオープン失敗: レスポンスに'channel'または'id'がありません")
                return None
        except SlackApiError as e:
            logging.error(f"[Slackエラー] DMチャンネルオープン失敗: {e.response['error']}")
            return None

    def send_message(self, message: str, channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> str:
        try:
            if not channel_id and not self.user_id:
                raise ValueError("送信先が指定されていません")

            channel = channel_id or self._get_dm_channel_id()
            if not channel:
                logging.error("[Slackエラー] チャンネルIDが取得できませんでした")
                return ""
            response = self.client.chat_postMessage(
                channel=channel,
                text=message,
                thread_ts=thread_ts
            )
            ts = response.get("ts", "")
            logging.info(f"[✅] メッセージ送信成功（ts={ts}）")
            return ts if isinstance(ts, str) else ""
        except SlackApiError as e:
            logging.error(f"[Slackエラー] メッセージ送信失敗: {e.response['error']}")
            return ""
        except Exception as e:
            logging.exception(f"[Slackエラー] 不明なエラー: {e}")
            return ""

    def send_file(self, filepath: str, title: str = "", comment: str = "",
                  channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> bool:
        if not os.path.exists(filepath):
            logging.error(f"[エラー] ファイルが存在しません: {filepath}")
            return False

        try:
            channel = channel_id or self._get_dm_channel_id()
            if not channel:
                logging.error("[Slackエラー] チャンネルIDが取得できませんでした")
                return False
            rendered_comment = self._render_template(comment)
            rendered_title = self._render_template(title)

            self.client.files_upload_v2(
                channel=channel,
                file=filepath,
                title=rendered_title,
                filename=os.path.basename(filepath),
                initial_comment=rendered_comment,
                thread_ts=thread_ts
            )
            logging.info(f"[✅] ファイル送信成功: {os.path.basename(filepath)}")
            return True
        except SlackApiError as e:
            logging.error(f"[Slackエラー] ファイル送信失敗: {e.response['error']}")
            return False

    def send_files(self, filepaths: List[str], title_template: str = "", comment_template: str = "",
                   channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> List[Tuple[str, bool]]:
        results = []
        for path in filepaths:
            success = self.send_file(
                filepath=path,
                title=title_template,
                comment=comment_template,
                channel_id=channel_id,
                thread_ts=thread_ts
            )
            results.append((path, success))
        return results

    def _render_template(self, text: str) -> str:
        now = datetime.now()
        return text.format(
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S")
        )

#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime

# 通知ログのディレクトリとパス
LOG_DIR = os.path.join(os.path.dirname(__file__), 'log')
NOTIFY_LOG = os.path.join(LOG_DIR, 'notify_history.log')


def setup_logging(log_file_path=None, to_stdout=False, log_level=logging.INFO):

    if logging.getLogger().hasHandlers():
        return  # すでに設定済みの場合は何もしない
    handlers = []

    if log_file_path:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        handlers.append(logging.FileHandler(log_file_path, encoding='utf-8'))

    if to_stdout:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers
    )


def append_or_replace_log_line(summary_line: str):
    """Slack通知成功ログを追記する（上書きしない）"""
    os.makedirs(LOG_DIR, exist_ok=True)
    now = datetime.now()
    new_line = f"{now.strftime('%Y-%m-%d %H:%M')} | {summary_line}"
    with open(NOTIFY_LOG, "a", encoding="utf-8") as f:
        f.write(new_line + "\n")


def log_no_notification(reason: str):
    """Slack通知対象外の理由をログに記録"""
    os.makedirs(LOG_DIR, exist_ok=True)
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    new_line = f"{today_str} {time_str} | 通知なし: {reason}"
    with open(NOTIFY_LOG, "a", encoding="utf-8") as f:
        f.write(new_line + "\n")

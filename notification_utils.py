#!/usr/bin/env python3
import os
from datetime import datetime
import glob
import logging

BASE_DIR = os.path.dirname(__file__)
FLAG_DIR = os.path.join(BASE_DIR, "notified_flags")
FLAG_EXT = ".flag"
NOTIFY_THRESHOLDS = [60, 70, 80, 90, 100]
DEPT_NOTIFY_FORCE_THRESHOLD=95

def get_flag_path(employee_code: str, threshold: int) -> str:
    os.makedirs(FLAG_DIR, exist_ok=True)
    year, week, _ = datetime.today().isocalendar()
    return os.path.join(FLAG_DIR, f"{employee_code}_{year}_{week}_{threshold}{FLAG_EXT}")


def already_notified_this_week(employee_code: str, threshold: int) -> bool:
    path = get_flag_path(employee_code, threshold)
    return os.path.exists(path)


def set_notified_flag_today(employee_code: str, threshold: int):
    path = get_flag_path(employee_code, threshold)
    with open(path, "w", encoding="utf-8") as f:
        f.write(datetime.today().strftime("%Y-%m-%d"))


def cleanup_old_flags():
    current_year, current_week, _ = datetime.today().isocalendar()
    if not os.path.exists(FLAG_DIR):
        return

    for path in glob.glob(os.path.join(FLAG_DIR, f"*{FLAG_EXT}")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = f.read().strip()
            try:
                saved_date = datetime.strptime(saved, "%Y-%m-%d")
            except ValueError:
                logging.warning(
                    f"[無効な日付形式] フラグ破損または不正な書式: {path} の内容: {repr(saved)}")
                continue
            saved_year, saved_week, _ = saved_date.isocalendar()

            # 年と週の両方が現在と異なる場合のみ削除
            if (saved_year != current_year) or (saved_week != current_week):
                os.remove(path)
        except Exception as e:
            logging.warning(f"[削除失敗] {path}: {e}")

def should_notify(percent_target: int, employee_code: str) -> int | None:
    """
    通知すべき閾値を返す。通常は週1回まで。
    ただし DEPT_NOTIFY_FORCE_THRESHOLD（例:95）以上はフラグを無視して毎回通知。
    """
    for threshold in sorted(NOTIFY_THRESHOLDS):
        if percent_target >= threshold:
            if threshold >= DEPT_NOTIFY_FORCE_THRESHOLD:
                return threshold
            if not already_notified_this_week(employee_code, threshold):
                return threshold
    return None

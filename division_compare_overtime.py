#!/usr/bin/env python3
import os
import csv
from datetime import datetime
import jpholiday
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import requests
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from slack_notifier import SlackNotifier
from notification_utils import should_notify, set_notified_flag_today, cleanup_old_flags
from log_utils import setup_logging, append_or_replace_log_line, log_no_notification
import logging
from overtime_result_saver import save_results_to_json
from collections import defaultdict


def is_force_notify_time() -> bool:
    if os.getenv("FORCE_NOTIFY_ALWAYS", "false").lower() == "true":
        logging.info("⏰ FORCE_NOTIFY_ALWAYS により、時刻判定をスキップして常時強制通知を実行します")
        return True

    try:
        today = datetime.today()
        weekday = today.weekday()  # 0=月, ..., 6=日
        hour = today.hour
        minute = today.minute

        force_day = int(os.getenv("FORCE_NOTIFY_DAY", "-1"))
        force_hour = int(os.getenv("FORCE_NOTIFY_HOUR", "-1"))
        force_minute = int(os.getenv("FORCE_NOTIFY_MINUTE", "-1"))
        window = int(os.getenv("FORCE_NOTIFY_WINDOW", "0"))

        if (weekday == force_day and
            hour == force_hour and
                abs(minute - force_minute) <= window):
            logging.info(f"⏰ 強制通知モード（全員通知）が有効です（{weekday}曜 {hour}:{minute}）")
            return True
    except Exception as e:
        logging.warning(f"⚠️ 強制通知時刻の判定に失敗しました: {e}")

    return False


@dataclass
class EmployeeInfo:
    code: str
    key: str
    last_name: str
    first_name: str
    division_code: str
    email: str
    overtime_target: Optional[int] = None

    @property
    def full_name(self) -> str:
        return f"{self.last_name}{self.first_name}"


@dataclass
class OvertimeResult:
    employee: EmployeeInfo
    current_overtime: int
    last_overtime: int
    target_overtime: int

    @property
    def percent_vs_last(self) -> int:
        return calculate_percentage(self.current_overtime, self.last_overtime)

    @property
    def percent_target(self) -> int:
        return calculate_percentage(self.current_overtime, self.target_overtime)

    @property
    def remaining_overtime(self) -> int:
        return self.target_overtime - self.current_overtime

    @property
    def is_over_target(self) -> bool:
        return self.current_overtime > self.target_overtime

    def format_report(self):
        current_month = format_date_string(0)
        last_month = format_date_string(-1)

        def to_hhmm(minutes: int) -> str:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}:{mins:02d}"

        status = self._get_status_message()
        over_minutes = abs(self.remaining_overtime)

        line1 = f"👤 {self.employee.full_name} {status}"
        line2 = f"🗓️ 今月({current_month}) 残業 {to_hhmm(self.current_overtime)}"
        if self.is_over_target:
            over_minutes = abs(self.remaining_overtime)
            line3 = f"📊 上限比 {self.percent_target}％ 🔥 上限超過: +{to_hhmm(over_minutes)}"
        else:
            line3 = f"📊 上限比 {self.percent_target}％ ⌛ 上限まで {to_hhmm(self.remaining_overtime)}"
        line4 = f"🔙 前月残業 {to_hhmm(self.last_overtime)} 前月比 {self.percent_vs_last}%"

        return "\n".join([line1, line2, line3, line4])

    def _get_status_message(self) -> str:
        if self.percent_target >= 100:
            return "🚨 上限100%超過"
        elif self.percent_target >= 90:
            return "⚠️ 警告:90%超過"
        elif self.percent_target >= 80:
            return "⚠️ 注意:80%超過"
        elif self.percent_target >= 70:
            return "📙 注意: 70%超過"
        elif self.percent_target >= 60:
            return "📗 備考: 60%超過"
        elif self.percent_target >= 50:
            return "📘 備考: 50%超過"
        return "✅ 問題なし"


class ConfigManager:
    @staticmethod
    def load_config() -> Dict[str, Any]:
        load_dotenv()
        config = {
            'base_url': os.getenv('KINGOFTIME_BASE_URL', 'https://api.kingtime.jp/v1.0'),
            'endpoint': os.getenv('KINGOFTIME_ENDPOINT', '/monthly-workings'),
            'token': os.getenv('KINGOFTIME_TOKEN'),
            'default_overtime': int(os.getenv('OVERTIME_TARGET_DEFAULT', '600')),
            'force_notify': os.getenv('DEBUG_FORCE_NOTIFY', 'false').lower() == 'true'
        }
        division_settings = os.getenv('OVERTIME_TARGET_DIVISION', '')
        config['division_overtime'] = ConfigManager._parse_division_settings(
            division_settings)
        return config

    @staticmethod
    def _parse_division_settings(settings_str: str) -> Dict[str, int]:
        division_settings = {}
        if settings_str:
            for setting in settings_str.split(','):
                if ':' in setting:
                    division, target = setting.split(':')
                    try:
                        division_settings[division.strip()] = int(
                            target.strip())
                    except ValueError:
                        logging.warning(f"無効な設定が無視されました: {setting}")
        return division_settings


class EmployeeLoader:
    @staticmethod
    def _parse_optional_int(value: Optional[str], field_name: str, employee_code: str) -> Optional[int]:
        if value is None or str(value).strip() == "":
            return None
        try:
            parsed = int(str(value).strip())
            if parsed < 0:
                logging.warning(f"無効な{field_name}が無視されました: 社員番号={employee_code}, 値={value}")
                return None
            return parsed
        except ValueError:
            logging.warning(f"無効な{field_name}が無視されました: 社員番号={employee_code}, 値={value}")
            return None

    @staticmethod
    def load_employees(filepath: str) -> List[EmployeeInfo]:
        if not os.path.exists(filepath):
            logging.critical(f"❌ 社員情報ファイルが見つかりません: {filepath}")
            raise FileNotFoundError(f"社員情報ファイルが存在しません: {filepath}")
        employees = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                employee_code = row['社員番号'].strip()
                employees.append(EmployeeInfo(
                    code=employee_code,
                    key=row['キー'].strip(),
                    last_name=row['氏'].strip(),
                    first_name=row['名'].strip(),
                    division_code=row['部署コード'].strip(),
                    email=row['メールアドレス'].strip(),
                    overtime_target=EmployeeLoader._parse_optional_int(
                        row.get('個人別残業上限分'),
                        '個人別残業上限分',
                        employee_code
                    )
                ))
        return employees


class KingOfTimeAPI:
    def __init__(self, config: Dict[str, Any]):
        self.base_url = config['base_url']
        self.endpoint = config['endpoint']
        self.headers = {
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json; charset=utf-8"
        }

    def get_overtime(self, year_month: str, division: str, employee_key: str) -> Optional[int]:
        url = f"{self.base_url}{self.endpoint}/{year_month}"
        params = {"division": division}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                for record in data:
                    if record.get("employeeKey") == employee_key:
                        overtime = record.get("overtime", 0)
                        night_overtime = record.get("nightOvertime", 0)
                        return overtime + night_overtime
            return 0
        except Exception as e:
            logging.error(f"APIエラーが発生しました: {e}")
            return None


class OvertimeAnalyzer:
    def __init__(self, api: KingOfTimeAPI, config: Dict[str, Any]):
        self.api = api
        self.default_target = config['default_overtime']
        self.division_targets = config['division_overtime']

    def get_target_overtime(self, employee: EmployeeInfo) -> int:
        # 判定優先順位: 個人別上限 > 部署別上限 > デフォルト上限
        if employee.overtime_target is not None:
            return employee.overtime_target
        return self.division_targets.get(employee.division_code, self.default_target)

    def analyze(self, employee: EmployeeInfo) -> Optional[OvertimeResult]:
        this_month = format_date_string(0, "%Y-%m")
        last_month = format_date_string(-1, "%Y-%m")
        current_overtime = self.api.get_overtime(
            this_month, employee.division_code, employee.key)
        last_overtime = self.api.get_overtime(
            last_month, employee.division_code, employee.key)
        if current_overtime is None or last_overtime is None:
            return None
        target_overtime = self.get_target_overtime(employee)
        return OvertimeResult(employee, current_overtime, last_overtime, target_overtime)


def format_date_string(offset_months: int, format_str: str = "%Y-%m") -> str:
    target_date = datetime.today() + relativedelta(months=offset_months)
    return target_date.strftime(format_str)


def calculate_percentage(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    return round((numerator / denominator) * 100)


def parse_department_email_mapping(mapping_str: str) -> Dict[str, List[str]]:
    mappings = {}
    if not mapping_str:
        return mappings
    for pair in mapping_str.split(','):
        if ':' in pair:
            depts, email = pair.split(':', 1)
            email = email.strip()
            for dept in depts.split(','):
                dept = dept.strip()
                if dept:
                    mappings.setdefault(dept, []).append(email)
    return mappings


def is_skip_day(today: datetime) -> bool:
    """土日祝判定（Trueならスキップすべき日）"""
    return today.weekday() >= 5 or jpholiday.is_holiday(today)


def main():
    try:
        today = datetime.today()

        # 強制通知判定は is_skip_day() の前に評価される必要がある
        if is_skip_day(today) and not is_force_notify_time():
            print("⛔ 土日祝日のため通知スキップ")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(script_dir, "log", "overtime_runner.log")

        setup_logging(log_file_path=log_path, to_stdout=True)
        load_dotenv()
        enable_self_notify = os.getenv(
            "ENABLE_SELF_NOTIFY", "false").lower() == "true"
        enabled_codes_str = os.getenv("SELF_NOTIFY_ENABLED_CODES", "")
        enabled_codes = set(code.strip()
                            for code in enabled_codes_str.split(",") if code.strip())
        config = ConfigManager.load_config()

        if is_force_notify_time():
            config['force_notify'] = True
            day_map = ['月', '火', '水', '木', '金', '土', '日']
            day_label = day_map[int(os.getenv("FORCE_NOTIFY_DAY", 5)) % 7]
            hour = os.getenv("FORCE_NOTIFY_HOUR", "21")
            minute = os.getenv("FORCE_NOTIFY_MINUTE", "30")
            logging.info(f"⏰ 強制通知モード（全員通知）が有効です（{day_label}曜{hour}:{minute}）")

        slack_token = os.getenv('SLACK_BOT_TOKEN')
        mapping_str = os.getenv('DEPARTMENT_EMAIL_MAPPING')
        if not slack_token or not mapping_str:
            raise ValueError("Slack設定が不完全です")

        # フラグの週次クリーンアップを最初に実行
        cleanup_old_flags()

        dept_email_mappings = parse_department_email_mapping(mapping_str)
        email_summary_map = defaultdict(list)

        department_reports = {}
        results_to_save = []
        notification_candidates = []

        script_dir = os.path.dirname(os.path.abspath(__file__))
        employee_file = os.path.join(script_dir, 'employeeKey.csv')
        employees = EmployeeLoader.load_employees(employee_file)
        api = KingOfTimeAPI(config)
        analyzer = OvertimeAnalyzer(api, config)

        for employee in employees:
            result = analyzer.analyze(employee)
            if result:
                results_to_save.append(result)
                # force_notify時は必ず100%で通知、それ以外はshould_notifyの戻り値
                threshold = 100 if config['force_notify'] else should_notify(
                    result.percent_target, employee.code)
                if threshold:
                    dept = employee.division_code
                    report = result.format_report()
                    if dept not in department_reports:
                        department_reports[dept] = []
                    department_reports[dept].append(report)
                    notification_candidates.append(
                        (employee.full_name, result.percent_target))
                    set_notified_flag_today(employee.code, threshold)

                    # メール別サマリ構築
                    for dept_key in [employee.division_code, "ALL"]:
                        for email in dept_email_mappings.get(dept_key, []):
                            email_summary_map[email].append(
                                (employee.full_name, result.percent_target))

                    # .envから強制本人通知しきい値を取得
                    force_self_threshold = int(
                        os.getenv("SELF_NOTIFY_FORCE_THRESHOLD", "90"))
                    percent = result.percent_target

                    # 強制本人通知対象かどうか
                    should_force_notify_self = enable_self_notify and percent >= force_self_threshold and employee.email
                    # 通常の本人通知対象かどうか
                    should_regular_notify_self = enable_self_notify and employee.code in enabled_codes and employee.email

                    # ✅ 本人にSlack DM通知を送信
                    if should_force_notify_self or should_regular_notify_self:
                        self_notifier = SlackNotifier(
                            slack_token, employee.email)
                        self_message = f"{employee.full_name}さんの残業状況レポート\n\n" + report
                        success = self_notifier.send_message(self_message)
                        if success:
                            logging.info(
                                f"[👤本人通知] ✅ {employee.email} へのSlack通知完了")
                            mode = "強制通知" if should_force_notify_self else "通常通知"
                            summary = f"Slack本人通知（{mode}）: {employee.email} | 対象: {employee.full_name}（{percent}％）"
                            append_or_replace_log_line(summary)
                        else:
                            logging.warning(
                                f"[👤本人通知] ⚠️ {employee.email} へのSlack通知失敗")

                else:
                    reason = f"{employee.full_name}（{result.percent_target}%）通知条件未達"
                    log_no_notification(reason)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, "cache")
        save_results_to_json(results_to_save, output_dir=output_dir)
        logging.info(f"📁 JSON保存先: {output_dir}")

        if not department_reports:
            logging.warning("⚠️ 通知対象者が存在しませんでした。Slack送信は行われません。")
        else:
            logging.info("Slack通知の送信を開始します...")
            sent_to = set()
            all_recipients = dept_email_mappings.get("ALL", [])

            for dept, reports in department_reports.items():
                recipients = dept_email_mappings.get(dept, []) + all_recipients
                for email in recipients:
                    if email not in sent_to:
                        user_reports = []
                        for d, r in department_reports.items():
                            if email in dept_email_mappings.get(d, []) or email in all_recipients:
                                user_reports.extend(r)

                        if user_reports:
                            notifier = SlackNotifier(slack_token, email)
                            message = "残業時間レポート\n" + "="*29 + "\n\n"
                            message += "\n\n".join(user_reports)
                            success = notifier.send_message(message)
                            notified_summaries = [
                                f"{name}（{percent}％）"
                                for name, percent in notification_candidates
                                if email in dept_email_mappings.get(dept, []) or email in all_recipients
                            ]
                            summary = f"Slack通知先: {email} | 通知件数: {len(user_reports)} | 対象: {', '.join(notified_summaries)}"

                            if success:
                                logging.info(f"✅ {email} への送信成功")
                                append_or_replace_log_line(summary)
                                sent_to.add(email)
                            else:
                                logging.error(f"❌ {email} への送信失敗")

            logging.info("Slack通知の送信が完了しました")

            # ▼ 通知先ごとのサマリログ出力（通知条件を満たした社員のみ）
            for email, summaries in email_summary_map.items():
                if not summaries:
                    continue
                notified_summary_strs = [
                    f"{name}（{percent}％）" for name, percent in summaries]
                summary = f"📝内容: {email} | 通知件数: {len(summaries)} | 対象: {', '.join(notified_summary_strs)}"
                append_or_replace_log_line(summary)

    except Exception as e:
        logging.exception(f"エラーが発生しました")


if __name__ == "__main__":
    main()

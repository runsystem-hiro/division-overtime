#!/usr/bin/env python3
import os
import json
from datetime import datetime
from typing import TYPE_CHECKING, List
import logging

if TYPE_CHECKING:
    from division_compare_overtime import OvertimeResult

def save_results_to_json(results: List["OvertimeResult"], output_dir="cache"):
    """
    OvertimeResultリストをJSONファイルに保存
    ※型ヒントは文字列で遅延評価し、循環importを回避
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = f"overtime_result_{datetime.today().strftime('%Y%m')}.json"
    output_path = os.path.join(output_dir, filename)

    output_data = {
        r.employee.code: {
            "name": r.employee.full_name,
            "division": r.employee.division_code,
            "current": r.current_overtime,
            "last": r.last_overtime,
            "target": r.target_overtime,
            "percent_vs_last": r.percent_vs_last,
            "percent_target": r.percent_target
        }
        for r in results
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ 分析結果を保存しました: {output_path}")

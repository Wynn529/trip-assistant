"""UTF-8 CSV exports for itinerary and simulated expenses."""

from __future__ import annotations

import csv
from io import StringIO


def _csv_bytes(rows: list[list[str]]) -> bytes:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def itinerary_csv(response: dict) -> bytes:
    rows = [["天数", "日期", "景点", "费用估算/人", "雨天状态", "备注"]]
    for day in response.get("itinerary", []):
        for activity in day.get("activities", []):
            rows.append(
                [
                    str(day["day"]),
                    day.get("date", ""),
                    activity["name"],
                    "未核实" if activity.get("price_per_person") is None else str(activity["price_per_person"]),
                    day.get("rain_source", ""),
                    day.get("note", ""),
                ]
            )
    return _csv_bytes(rows)


def expense_csv(expenses: list[dict]) -> bytes:
    rows = [["日期", "类别", "金额", "备注", "凭证状态"]]
    for expense in expenses:
        rows.append(
            [
                str(expense.get("date", "")),
                str(expense.get("category", "")),
                str(expense.get("amount", "")),
                str(expense.get("note", "")),
                "模拟记录，未上传真实凭证",
            ]
        )
    rows.append(["", "合计", str(sum(int(item.get("amount", 0)) for item in expenses)), "", ""])
    return _csv_bytes(rows)

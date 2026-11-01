# 自动报表：读 CSV → 本地统计 → 交给大模型写成周报。
# 关键点：数字先算准，模型只负责组织语言。不让模型算数，它容易编。
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CSV = os.path.join(ROOT, "data", "sales.csv")


def load_rows(path=DEFAULT_CSV):
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    rows = []
    # utf-8-sig 是为了兼容 Excel 另存的带 BOM 的 CSV
    with open(path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def summarize(rows):
    total = 0.0
    by_region = {}
    by_month = {}
    for row in rows:
        amount = float(row["amount"])
        total += amount
        by_region[row["region"]] = by_region.get(row["region"], 0.0) + amount
        by_month[row["month"]] = by_month.get(row["month"], 0.0) + amount
    return {
        "count": len(rows),
        "total": total,
        "by_region": by_region,
        "by_month": by_month,
    }


def build_prompt(summary):
    ranked = sorted(summary["by_region"].items(), key=lambda kv: -kv[1])
    lines = [
        "以下是本月销售数据的统计结果，请写一份给部门主管看的中文周报。",
        "要求：200 字以内；先说整体情况，再点出最高和最低的区域，最后给一条具体可执行的建议。",
        "不要重复罗列数字，用人话总结趋势。",
        "",
        "【硬性要求】下面的数字已经算好了，直接引用原文，"
        "不要做单位换算（元→万元），也不要重新计算，否则容易出错。",
        "",
        "总销售额：%.2f 元" % summary["total"],
        "订单数：%d" % summary["count"],
    ]
    for region, amount in ranked:
        pct = amount / summary["total"] * 100 if summary["total"] else 0
        lines.append("区域 %s：%.2f 元（占比 %.1f%%）" % (region, amount, pct))
    return "\n".join(lines)


def to_markdown(summary, ai_text, title="销售周报"):
    """把统计表 + 模型生成的正文拼成一份可以直接贴到周会文档里的 Markdown。"""
    ranked = sorted(summary["by_region"].items(), key=lambda kv: -kv[1])
    out = ["# %s" % title, "", ai_text.strip(), "", "## 数据明细", "",
           "| 区域 | 销售额（元） | 占比 |", "| --- | ---: | ---: |"]
    for region, amount in ranked:
        pct = amount / summary["total"] * 100 if summary["total"] else 0
        out.append("| %s | %.2f | %.1f%% |" % (region, amount, pct))
    out.append("| **合计** | **%.2f** | 100.0%% |" % summary["total"])
    return "\n".join(out)

# 命令行入口。
# 用法：
#   python src/main.py ask "报销需要什么材料"
#   python src/main.py report
#   python src/main.py eval
#   python src/main.py logs
import os
import sys

# 让 python src/main.py 也能 import 同目录的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval as eval_mod
import kb
import llm
import report

USAGE = """用法：
  python src/main.py ask "你的问题"     提问
  python src/main.py report            生成销售周报
  python src/main.py eval [测试集路径]  跑检索效果测试
  python src/main.py logs              查看历史问答"""


def cmd_ask(question):
    hits = kb.search(question, top_k=2)
    messages = kb.build_messages(question, hits)

    if hits:
        print("检索到的资料：")
        for score, name, para in hits:
            preview = para.replace("\n", " ")[:40]
            print("  - %s（相似度 %.2f）：%s……" % (name, score, preview))
    else:
        print("检索到的资料：无")
    print()

    answer = llm.chat(messages)
    print(answer)

    source = hits[0][1] if hits else ""
    score = hits[0][0] if hits else 0.0
    kb.log_qa(question, answer, source, score)


def cmd_report():
    rows = report.load_rows()
    summary = report.summarize(rows)
    print("已读取 %d 条记录，总销售额 %.2f 元" % (summary["count"], summary["total"]))
    print("正在生成周报……\n")

    text = llm.chat([{"role": "user", "content": report.build_prompt(summary)}])
    md = report.to_markdown(summary, text, title="销售周报")

    out_path = os.path.join(report.ROOT, "data", "weekly_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print("\n已保存到 data/weekly_report.md")


def cmd_eval():
    # 不传参数就跑规范表述那组；也可以指定别的测试集
    path = sys.argv[2] if len(sys.argv) > 2 else eval_mod.QUESTIONS
    print("测试集：%s\n" % os.path.basename(path))
    eval_mod.run(path)


def cmd_logs():
    rows = kb.recent_logs(10)
    if not rows:
        print("还没有问答记录。")
        return
    print("最近 10 条问答记录：")
    for question, source, score, created in rows:
        print("  [%s] %s  <- %s  相似度 %.3f" % (created, question, source or "无", score))

    weak = kb.low_quality_logs()
    if weak:
        print("\n以下问题检索质量偏低，建议补充文档：")
        for question, score in weak:
            print("  %s（%.3f）" % (question, score))


def main():
    if len(sys.argv) < 2:
        print(USAGE)
        return

    action = sys.argv[1]
    if action == "ask":
        if len(sys.argv) < 3:
            print('用法：python src/main.py ask "你的问题"')
            return
        cmd_ask(" ".join(sys.argv[2:]))
    elif action == "report":
        cmd_report()
    elif action == "eval":
        cmd_eval()
    elif action == "logs":
        cmd_logs()
    else:
        print("未知命令：%s" % action)
        print(USAGE)


if __name__ == "__main__":
    main()

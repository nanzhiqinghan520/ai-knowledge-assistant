# 效果测试：跑一遍预先标好答案的问题集，看检索有没有命中期望的文档。
# 这是 AI 应用上线前必须做的一步——不然你不知道它是真的答对了，还是碰巧。
import json
import os

from kb import search

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.path.join(ROOT, "tests", "questions.json")


def run(path=QUESTIONS, top_k=2, verbose=True):
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    hit = 0
    rows = []
    for case in cases:
        results = search(case["question"], top_k=top_k)
        got = [name for _, name, _ in results]
        ok = case["expect_doc"] in got
        if ok:
            hit += 1
        rows.append((ok, case["question"], case["expect_doc"], got))

    if verbose:
        for ok, question, expect, got in rows:
            flag = "PASS" if ok else "FAIL"
            print("[%s] %s" % (flag, question))
            if not ok:
                print("       期望：%s   实际：%s" % (expect, got or "无命中"))

    rate = hit / float(len(cases)) * 100 if cases else 0.0
    print("\n检索命中率：%d/%d = %.1f%%" % (hit, len(cases), rate))
    return hit, len(cases)

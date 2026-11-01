# 单元测试。用标准库 unittest，不需要装 pytest。
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import kb
import llm
import report


class TestBigrams(unittest.TestCase):
    """字符二元组是检索的地基，先测它。"""

    def test_basic(self):
        self.assertEqual(kb._bigrams("报销"), {"报销"})

    def test_three_chars(self):
        self.assertEqual(kb._bigrams("报销标"), {"报销", "销标"})

    def test_empty(self):
        self.assertEqual(kb._bigrams(""), set())

    def test_single_char_has_no_gram(self):
        # 单个字切不出二元组，检索时会因为问题为空直接返回，不能崩
        self.assertEqual(kb._bigrams("假"), set())

    def test_whitespace_ignored(self):
        self.assertEqual(kb._bigrams("报 销"), kb._bigrams("报销"))


class TestChunking(unittest.TestCase):
    """分块策略。这里出错的表现是"文档在，但永远检索不到"。"""

    def setUp(self):
        self.chunks = kb.load_chunks()

    def test_chunks_not_empty(self):
        self.assertGreater(len(self.chunks), 10)

    def test_heading_prefixed(self):
        """含 500 元的那一段，前面必须带上"住宿标准"。

        不带标题的话这段里一个"住宿"都没有，就再也检索不到了。
        """
        matched = [text for _, text in self.chunks if "500" in text]
        self.assertTrue(matched, "没找到包含 500 元的段落")
        self.assertTrue(matched[0].startswith("住宿标准"),
                        "段落没有带上小标题：%s" % matched[0][:30])

    def test_short_paragraph_skipped(self):
        # 纯标题行不足 8 个字符，不应该单独成为一段
        for _, text in self.chunks:
            self.assertGreaterEqual(len(text), 8)

    def test_missing_dir_returns_empty(self):
        self.assertEqual(kb.load_chunks(os.path.join(ROOT, "no_such_dir")), [])


class TestSearch(unittest.TestCase):

    def test_hit_expected_doc(self):
        hits = kb.search("出差住宿费标准是多少")
        self.assertTrue(hits)
        self.assertEqual(hits[0][1], "01-报销制度.md")

    def test_second_question(self):
        hits = kb.search("陪产假多少天")
        self.assertTrue(hits)
        self.assertEqual(hits[0][1], "02-考勤与假期.md")

    def test_irrelevant_question_returns_nothing(self):
        # 知识库里没有股市，也没有任何字面重合，应该老老实实返回空
        self.assertEqual(kb.search("今天股市怎么样"), [])

    def test_known_limitation_false_positive(self):
        """已知缺陷：字面重合会带来误命中。

        "明天北京天气怎么样" 里有个"北京"，正好撞上报销制度里的城市列表，
        于是被判成命中（相似度 0.125）。这是纯字面匹配的天生缺陷——
        试过加"至少命中两个二元组"的规则，会把口语化测试集从 11/12 打到 4/12，
        代价太大，所以保留现状并在这里钉住。哪天换成语义检索，这条测试应该会失败。
        """
        hits = kb.search("明天北京天气怎么样")
        self.assertTrue(hits, "行为变了：这条曾经是误命中，如果现在返回空说明检索变好了")
        self.assertLess(hits[0][0], 0.2, "误命中的分数应该很低，不能排到前面去")

    def test_empty_question(self):
        self.assertEqual(kb.search(""), [])

    def test_top_k_respected(self):
        hits = kb.search("报销", top_k=1)
        self.assertLessEqual(len(hits), 1)

    def test_scores_sorted_desc(self):
        hits = kb.search("报销材料", top_k=3)
        scores = [s for s, _, _ in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestMessages(unittest.TestCase):

    def test_with_hits(self):
        hits = kb.search("出差住宿费标准是多少")
        msgs = kb.build_messages("出差住宿费标准是多少", hits)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("出差住宿费标准是多少", msgs[1]["content"])

    def test_without_hits_still_builds(self):
        msgs = kb.build_messages("随便问问", [])
        self.assertIn("没有检索到相关文档", msgs[1]["content"])

    def test_system_prompt_forbids_making_things_up(self):
        msgs = kb.build_messages("x", [])
        self.assertIn("不要编", msgs[0]["content"])


class TestReport(unittest.TestCase):

    def setUp(self):
        self.rows = report.load_rows()
        self.summary = report.summarize(self.rows)

    def test_row_count(self):
        self.assertEqual(len(self.rows), 12)

    def test_total_amount(self):
        self.assertAlmostEqual(self.summary["total"], 3599500.0, places=2)

    def test_region_split_sums_to_total(self):
        self.assertAlmostEqual(sum(self.summary["by_region"].values()),
                               self.summary["total"], places=2)

    def test_markdown_has_table_and_total(self):
        md = report.to_markdown(self.summary, "测试正文", title="周报")
        self.assertIn("# 周报", md)
        self.assertIn("测试正文", md)
        self.assertIn("合计", md)
        self.assertIn("3599500.00", md)

    def test_missing_csv_raises(self):
        with self.assertRaises(FileNotFoundError):
            report.load_rows(os.path.join(ROOT, "no_such.csv"))

    def test_prompt_forbids_unit_conversion(self):
        # 模型把 478500 写成 4.79 万那次之后加的硬性要求
        prompt = report.build_prompt(self.summary)
        self.assertIn("不要做单位换算", prompt)


class TestConfig(unittest.TestCase):

    def test_defaults_present(self):
        cfg = llm.load_config()
        for key in ("base_url", "model", "timeout", "retries"):
            self.assertIn(key, cfg)

    def test_bad_json_falls_back_to_defaults(self):
        original = llm.CONFIG_PATH
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        tmp.write("{bad json")
        tmp.close()
        try:
            llm.CONFIG_PATH = tmp.name
            cfg = llm.load_config()
            # 坏文件不能抛异常，要退回默认值并进模拟模式
            self.assertEqual(cfg["api_key"], "")
        finally:
            llm.CONFIG_PATH = original
            os.unlink(tmp.name)

    def test_env_var_overrides_model(self):
        original = llm.CONFIG_PATH
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"model": "file-model"}, tmp)
        tmp.close()
        os.environ["LLM_MODEL"] = "env-model"
        try:
            llm.CONFIG_PATH = tmp.name
            self.assertEqual(llm.load_config()["model"], "env-model")
        finally:
            llm.CONFIG_PATH = original
            del os.environ["LLM_MODEL"]
            os.unlink(tmp.name)


class TestDatabase(unittest.TestCase):
    """日志库用临时文件，别污染真实数据。"""

    def setUp(self):
        self.original = kb.DB_PATH
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.db_path)
        kb.DB_PATH = self.db_path

    def tearDown(self):
        kb.DB_PATH = self.original
        for suffix in ("", ".bak"):
            if os.path.exists(self.db_path + suffix):
                os.unlink(self.db_path + suffix)

    def test_log_and_read_back(self):
        kb.log_qa("测试问题", "测试回答", "01-报销制度.md", 0.5, 123.0)
        rows = kb.recent_logs(5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "测试问题")

    def test_stats_counts(self):
        kb.log_qa("q1", "a1", "doc", 0.5, 100.0)
        kb.log_qa("q2", "a2", "doc", 0.05, 200.0)
        s = kb.stats()
        self.assertEqual(s["total"], 2)
        self.assertAlmostEqual(s["avg_ms"], 150.0, places=1)

    def test_corrupted_db_is_rebuilt(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            f.write("this is not a database")
        # 不应该抛异常，而是备份后重建
        kb.log_qa("q", "a", "doc", 0.3, 10.0)
        self.assertTrue(os.path.exists(self.db_path + ".bak"))
        self.assertEqual(kb.stats()["total"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# 知识库模块：加载文档、检索相关段落、把每次问答写进 SQLite。
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_DIR = os.path.join(ROOT, "data", "docs")
DB_PATH = os.path.join(ROOT, "data", "history.db")


def _flush(chunks, doc_name, heading, lines):
    """把攒着的几行合成一个段落，并带上它所属的小标题。

    带标题这一步很关键：像"住宿标准"这种小标题下面的段落，
    正文里可能只有"一线城市每晚上限 500 元"，一个"住宿"都没有。
    如果切块时把标题丢掉，这段就永远检索不到。
    """
    text = " ".join(lines).strip()
    if len(text) < 8:
        return
    if heading:
        text = heading + " " + text
    chunks.append((doc_name, text))


def load_chunks(doc_dir=DOC_DIR):
    """把每份文档按空行切成段落，返回 [(文件名, 段落), ...]。

    切的粒度是段落而不是整篇：整篇太长塞不进 prompt，句子又太碎丢上下文。
    每段前面拼上所属小标题，避免段落脱离上下文后检索不到。
    """
    chunks = []
    if not os.path.isdir(doc_dir):
        return chunks

    for name in sorted(os.listdir(doc_dir)):
        if not name.endswith(".md"):
            continue

        with open(os.path.join(doc_dir, name), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        heading = ""
        buffer = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                _flush(chunks, name, heading, buffer)
                buffer = []
                heading = stripped.lstrip("#").strip()
            elif not stripped:
                _flush(chunks, name, heading, buffer)
                buffer = []
            else:
                buffer.append(stripped)
        _flush(chunks, name, heading, buffer)

    return chunks


def _bigrams(text):
    """切成字符二元组。

    中文没有空格，不装分词库的话，二元组是最省事又够用的近似方案。
    比如"报销标准" -> {报销, 销标, 标准}
    """
    text = re.sub(r"\s+", "", text)
    return set(text[i:i + 2] for i in range(len(text) - 1))


def search(question, top_k=2):
    """返回 [(相似度, 文件名, 段落), ...]，按相似度降序。

    相似度 = 问题与段落共有的二元组数 / 问题的二元组总数。
    简单粗暴，但对"企业内部问答"这种同义词不多的场景够用。
    """
    q_grams = _bigrams(question)
    if not q_grams:
        return []

    scored = []
    for name, para in load_chunks():
        p_grams = _bigrams(para)
        if not p_grams:
            continue
        score = len(q_grams & p_grams) / float(len(q_grams))
        if score > 0.08:               # 低于这个阈值基本是噪声
            scored.append((score, name, para))

    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def build_messages(question, hits):
    """把检索到的段落拼成 prompt。这是 RAG 最朴素的形态。"""
    if hits:
        context = "\n\n".join("[来源：%s]\n%s" % (name, para) for _, name, para in hits)
    else:
        context = "（没有检索到相关文档）"

    system = (
        "你是公司内部知识库助手。只能依据下面提供的资料回答，"
        "资料里没有的内容要直接说不知道，不要编。回答用中文，控制在 150 字以内。"
    )
    user = "资料：\n%s\n\n问题：%s" % (context, question)
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


# ---------- SQLite：记录问答，对应"日常运维与问题收集" ----------

def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS qa_log (
                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                   question   TEXT NOT NULL,
                   answer     TEXT,
                   source     TEXT,
                   score      REAL,
                   created_at TEXT DEFAULT CURRENT_TIMESTAMP
               )"""
        )
    except sqlite3.DatabaseError:
        # 文件被改坏或者根本不是数据库：备份后重建，别让日志拖垮整个程序
        conn.close()
        if os.path.exists(DB_PATH):
            os.replace(DB_PATH, DB_PATH + ".bak")
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS qa_log (
                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                   question   TEXT NOT NULL,
                   answer     TEXT,
                   source     TEXT,
                   score      REAL,
                   created_at TEXT DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        print("[提示] 问答记录库已损坏，原文件备份为 history.db.bak，已重建。")
    return conn


def log_qa(question, answer, source, score):
    conn = _connect()
    conn.execute(
        "INSERT INTO qa_log (question, answer, source, score) VALUES (?, ?, ?, ?)",
        (question, answer, source, score),
    )
    conn.commit()
    conn.close()


def recent_logs(limit=10):
    conn = _connect()
    rows = conn.execute(
        "SELECT question, source, ROUND(score, 3), created_at "
        "FROM qa_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def low_quality_logs(threshold=0.15, limit=10):
    """相似度很低的问题——说明知识库没覆盖，是需要补文档的信号。"""
    conn = _connect()
    rows = conn.execute(
        "SELECT question, ROUND(score, 3) FROM qa_log "
        "WHERE score < ? ORDER BY id DESC LIMIT ?", (threshold, limit)
    ).fetchall()
    conn.close()
    return rows

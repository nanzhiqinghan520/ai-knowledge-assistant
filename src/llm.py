# 大模型调用封装。
# 只依赖标准库，不需要 pip install，换台机器也能直接跑。
import json
import os
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_ready():
    return bool(load_config().get("api_key", "").strip())


def chat(messages, temperature=0.3, max_tokens=800):
    """调用 OpenAI 兼容格式的 /chat/completions。

    国内主流厂商（DeepSeek、通义、智谱）都提供兼容接口，
    所以换模型只要改 config.json 里的 base_url 和 model。
    """
    cfg = load_config()
    key = cfg.get("api_key", "").strip()
    if not key:
        return _mock_reply(messages)

    base_url = cfg.get("base_url", "https://api.deepseek.com").rstrip("/")
    model = cfg.get("model", "deepseek-chat")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:200]
        return "[调用失败] HTTP %s：%s" % (e.code, body)
    except Exception as e:
        return "[调用失败] %s" % e


def _mock_reply(messages):
    """没配 key 时的兜底，保证程序能跑通、能演示流程。"""
    question = ""
    for m in messages:
        if m["role"] == "user":
            question = m["content"]

    # 问答场景的 prompt 里带着资料，这里只把最后那句问题拎出来
    if "问题：" in question:
        question = question.split("问题：")[-1]
    elif "总销售额" in question:
        question = "（自动报表任务）"

    return (
        "【模拟模式】没有在 config.json 里找到 api_key，无法调用真实模型。\n"
        "问题：%s\n"
        "填好 api_key 后，这里会换成模型根据检索资料生成的回答。" % question.strip()[:120]
    )

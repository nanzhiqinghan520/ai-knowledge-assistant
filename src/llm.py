# 大模型调用封装。
# 只依赖标准库，不需要 pip install，换台机器也能直接跑。
import json
import os
import time
import urllib.error
import urllib.request

from logger import get_logger

log = get_logger("llm")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")

DEFAULTS = {
    "api_key": "",
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash",
    "timeout": 60,
    "retries": 2,
    "temperature": 0.3,
    "max_tokens": 800,
}

# 这些状态码是"等一会儿再试可能就好了"，其他错误重试没意义
RETRYABLE_STATUS = (429, 500, 502, 503, 504)


def load_config():
    """读配置。文件里的值可以被环境变量覆盖，方便部署时不改文件。

    优先级：环境变量 > config.json > 内置默认值。
    文件不存在或格式写坏了都当作"没配置"处理，不让程序崩。
    """
    cfg = dict(DEFAULTS)

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update({k: v for k, v in json.load(f).items()
                            if not k.startswith("_")})
        except (json.JSONDecodeError, OSError) as e:
            # 用户手改配置最容易多一个逗号少一个引号，这里兜住并给出位置
            print("[提示] config.json 读取失败：%s" % e)
            print("       本次按未配置处理（进模拟模式）。")
            log.error("读取 config.json 失败：%s", e)

    for env_name, key in (("LLM_API_KEY", "api_key"),
                          ("LLM_BASE_URL", "base_url"),
                          ("LLM_MODEL", "model")):
        value = os.environ.get(env_name)
        if value:
            cfg[key] = value
            log.info("配置被环境变量 %s 覆盖", env_name)

    return cfg


def is_ready():
    return bool(str(load_config().get("api_key", "")).strip())


def chat(messages, temperature=None, max_tokens=None):
    """调用 OpenAI 兼容格式的 /chat/completions。

    国内主流厂商（智谱、硅基流动、DeepSeek、通义）都提供兼容接口，
    所以换模型只要改配置里的 base_url 和 model。

    网络抖动或限流会自动重试，间隔按 1s、2s 递增。
    """
    cfg = load_config()
    key = str(cfg.get("api_key", "")).strip()
    if not key:
        return _mock_reply(messages)

    base_url = str(cfg.get("base_url", "")).rstrip("/")
    payload = {
        "model": cfg.get("model", ""),
        "messages": messages,
        "temperature": temperature if temperature is not None else cfg.get("temperature", 0.3),
        "max_tokens": max_tokens if max_tokens is not None else cfg.get("max_tokens", 800),
    }
    body = json.dumps(payload).encode("utf-8")
    timeout = float(cfg.get("timeout", 60))
    retries = int(cfg.get("retries", 2))

    last_error = ""
    for attempt in range(retries + 1):
        started = time.time()
        req = urllib.request.Request(
            base_url + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"].strip()
            log.info("调用成功 model=%s 耗时=%.0fms 重试=%d",
                     payload["model"], (time.time() - started) * 1000, attempt)
            return text

        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:200]
            last_error = "HTTP %s：%s" % (e.code, detail)
            log.warning("调用失败 model=%s 第%d次 code=%s",
                        payload["model"], attempt + 1, e.code)
            if e.code not in RETRYABLE_STATUS or attempt >= retries:
                return "[调用失败] " + last_error

        except Exception as e:          # 超时、DNS 失败等
            last_error = str(e)
            log.warning("调用异常 model=%s 第%d次 %s",
                        payload["model"], attempt + 1, e)
            if attempt >= retries:
                return "[调用失败] " + last_error

        time.sleep(2 ** attempt)        # 1s、2s、4s

    return "[调用失败] " + last_error


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

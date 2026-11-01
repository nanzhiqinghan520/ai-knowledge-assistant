# 统一日志。
# 控制台只输出用户要看的业务信息，过程细节统一写日志文件，出问题能回溯。
import logging
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

_root = logging.getLogger("kbassistant")
_configured = False


def get_logger(name="app"):
    global _configured
    if not _configured:
        os.makedirs(LOG_DIR, exist_ok=True)
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)-10s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(fmt)
        _root.setLevel(logging.INFO)
        if not _root.handlers:
            _root.addHandler(handler)
        _configured = True
    return logging.getLogger("kbassistant." + name)

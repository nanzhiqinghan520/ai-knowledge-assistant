# 一个能跑的最简镜像。Python 标准库够用，不需要 pip install。
# 构建：docker build -t kb-assistant .
# 运行：docker run --rm -e LLM_API_KEY=你的key kb-assistant ask "出差住宿标准"
FROM python:3.11-slim

WORKDIR /app

COPY src/ ./src/
COPY data/ ./data/
COPY tests/ ./tests/
COPY config.example.json ./

# 日志实时输出，不要被缓冲吃掉
ENV PYTHONUNBUFFERED=1

# 密钥通过环境变量注入，不打进镜像
ENTRYPOINT ["python", "src/main.py"]

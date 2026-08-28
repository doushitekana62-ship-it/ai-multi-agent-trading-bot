FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ai_engine/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# The frontend build step copies these directories into the Workers build root
# before Wrangler builds the Container image.
COPY agents /app/agents
COPY core /app/core
COPY exchange_integration /app/exchange_integration
COPY ai_engine/app.py /app/app.py

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

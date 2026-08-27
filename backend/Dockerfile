FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY agents ./agents
COPY backend ./backend
COPY core ./core
COPY exchange_integration ./exchange_integration
COPY integration ./integration
COPY paper_trading ./paper_trading
COPY main.py api.py ./

EXPOSE 8000

CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]

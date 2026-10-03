FROM python:3.12.14-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY phase1_adk_spike ./phase1_adk_spike
COPY phase2_backend ./phase2_backend

EXPOSE 8080

CMD ["uvicorn", "phase2_backend.app:app", "--host", "0.0.0.0", "--port", "8080"]

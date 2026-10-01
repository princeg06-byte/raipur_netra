FROM python:3.12-slim

WORKDIR /app

# system deps for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY data ./data
# NOTE: models/yolo_raipur_best.pt is excluded from git (see .gitignore);
# mount it or bake it:  COPY models ./models

EXPOSE 8000
ENV RN_HOST=0.0.0.0 RN_PORT=8000 RN_WORKERS=1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim
WORKDIR /app
COPY common/ /app/common/
COPY services/search_api/requirements.txt /app/req.txt
RUN pip install --no-cache-dir -r /app/req.txt
COPY services/search_api/app.py /app/app.py
ENV PYTHONPATH=/app LOG_DB_PATH=/app/data/central_logs.db
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

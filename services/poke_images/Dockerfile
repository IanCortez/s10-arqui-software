FROM python:3.11-slim
WORKDIR /app
COPY common/ /app/common/
COPY services/poke_images/requirements.txt /app/req.txt
RUN pip install --no-cache-dir -r /app/req.txt
COPY services/poke_images/app.py /app/app.py
ENV PYTHONPATH=/app LOG_DIR=/app/logs
EXPOSE 8003
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]

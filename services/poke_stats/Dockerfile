FROM python:3.11-slim
WORKDIR /app
COPY common/ /app/common/
COPY services/poke_stats/requirements.txt /app/req.txt
RUN pip install --no-cache-dir -r /app/req.txt
COPY services/poke_stats/ /app/poke_stats/
RUN python /app/poke_stats/seed_db.py
ENV PYTHONPATH=/app LOG_DIR=/app/logs STATS_DB=/app/poke_stats/pokemon_stats.db
EXPOSE 8002
CMD ["uvicorn", "poke_stats.app:app", "--host", "0.0.0.0", "--port", "8002"]

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY version.json .
RUN chmod -R a+rX /app/app /app/version.json \
    && mkdir -p /app/contents \
    && chown 1000:1000 /app/contents \
    && chmod 700 /app/contents
USER 1000:1000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-5000}"]

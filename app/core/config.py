import os

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://searxng:8080")
TIMEOUT = int(os.getenv("SEARXNG_TIMEOUT", "5"))
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "5000"))

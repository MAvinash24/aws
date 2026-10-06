FROM library/python@sha256:9ce5a4e59b833c002e1c4196c60ec0b38977e3235d626298ba7ffe2e64f5a30c
WORKDIR /app
COPY app/ ./app/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]
CMD ["python", "-m", "app.server"]

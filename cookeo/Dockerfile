# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /opt/cookeo
COPY requirements.txt ./
RUN --mount=type=secret,id=build_ca,target=/run/secrets/build_ca.pem \
    if [ -f /run/secrets/build_ca.pem ]; then export PIP_CERT=/run/secrets/build_ca.pem; fi; \
    pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY resources ./resources
COPY THIRD_PARTY_LICENSE.txt ./
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health',timeout=3)"
CMD ["python", "-m", "app.server", "--data", "/data", "--bind", "0.0.0.0", "--port", "8099", "--ingress"]

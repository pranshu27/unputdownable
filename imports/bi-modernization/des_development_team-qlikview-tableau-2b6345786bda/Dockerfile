# Build Stage
FROM python:3.11-slim AS builder
 
WORKDIR /app
 
COPY requirements.txt .
 
RUN pip install \
    --no-cache-dir \
    --prefix=/python \
    "wheel>=0.46.2" \
    "jaraco.context>=6.1.0" \
    -r requirements.txt
 
COPY . .
 
# Runtime Stage
FROM 409344278376.dkr.ecr.us-east-2.amazonaws.com/python-hardened-image:v1
 
WORKDIR /app
 
COPY --from=builder /python /usr/local
COPY --from=builder /app /app

USER nonroot
 
CMD ["python", "app.py"]
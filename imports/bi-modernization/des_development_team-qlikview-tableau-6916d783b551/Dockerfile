# Builder
FROM python:3.11-slim AS builder

WORKDIR /usr/src/app

COPY pbip-converter-skill/requirements.txt .

RUN pip install --upgrade pip setuptools wheel

RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    -r requirements.txt

COPY pbip-converter-skill/ .

# Runtime
FROM 409344278376.dkr.ecr.us-east-2.amazonaws.com/python-hardened-image:v1

WORKDIR /usr/src/app

COPY --from=builder /install /usr/local

COPY --from=builder /usr/src/app .

EXPOSE 8004

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8004"]
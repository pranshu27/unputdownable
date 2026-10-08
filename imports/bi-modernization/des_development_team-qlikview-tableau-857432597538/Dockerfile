FROM python:3.13-slim AS builder

WORKDIR /usr/src/app

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel

RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    -r requirements.txt

COPY linker_agent/ ./linker_agent/

# Runtime
FROM 409344278376.dkr.ecr.us-east-2.amazonaws.com/python-hardened-image:v1

WORKDIR /usr/src/app

COPY --from=builder /install /usr/local

COPY --from=builder /usr/src/app .

EXPOSE 3005

CMD ["uvicorn", "linker_agent.api.main:app", "--host", "0.0.0.0", "--port", "3005"]
FROM python:3.11.13-slim AS builder

# Upgrade OS packages to patch any base image CVEs
RUN apt-get update && apt-get -y upgrade && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Upgrade the toolchain FIRST so requirements.txt resolves against patched code
RUN python3.11 -m pip install --no-cache-dir --upgrade \
    "pip>=25.2" \
    "setuptools>=80.9.0" \
    "wheel>=0.46.2" \
    "jaraco.context>=6.1.0"

# Copy and install Python dependencies into isolated prefix
COPY requirements.txt ./
RUN python3.11 -m pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && python3.11 -m pip install --no-cache-dir --prefix=/install --upgrade \
    "setuptools>=80.9.0" \
    "wheel>=0.46.2" \
    "jaraco.context>=6.1.0"

# Copy application code only — credentials are injected at runtime via env vars
COPY re_jira_endpoint.py ./

# Runtime
FROM 409344278376.dkr.ecr.us-east-2.amazonaws.com/python-hardened-image:v1

WORKDIR /usr/src/app

COPY --from=builder /install /usr/local

COPY --from=builder /usr/src/app .

EXPOSE 8003

CMD ["uvicorn", "re_jira_endpoint:app", "--host", "0.0.0.0", "--port", "8003"]
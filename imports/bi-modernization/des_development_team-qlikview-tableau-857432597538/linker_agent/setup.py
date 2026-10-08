"""
Setup configuration for Linker Agent package
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="linker-agent",
    version="1.0.0",
    author="Linker Agent Team",
    description="Intelligent data catalog linkage system with LLM-powered semantic matching",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "aiohttp>=3.13.0",
        "httpx>=0.28.0",
        "openai>=2.26.0",
        "pydantic>=2.12.0",
        "python-dotenv>=1.2.0",
        "tqdm>=4.67.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.4.0",
            "pytest-asyncio>=1.2.0",
            "pytest-cov>=7.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)

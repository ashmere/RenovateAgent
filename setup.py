"""
Setup script for the Renovate PR Assistant.
"""

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="renovate-agent",
    version="0.1.0",
    author="Renovate PR Assistant",
    author_email="support@example.com",
    description="AI-powered automation for Renovate dependency update PRs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/renovate-agent",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Version Control :: Git",
    ],
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.20.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "PyGithub>=1.55.0",
        "httpx>=0.24.0",
        "structlog>=23.0.0",
        "python-dotenv>=1.0.0",
        "cryptography>=40.0.0",
        "PyJWT>=2.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.20.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
            "pre-commit>=3.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "renovate-agent=renovate_agent.main:main",
        ],
    },
)

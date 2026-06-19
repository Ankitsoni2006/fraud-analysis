"""
setup.py — IVC Operational Risk Intelligence Platform
"""
from setuptools import setup, find_packages

setup(
    name="ivc-risk-platform",
    version="3.0.0",
    description="IVC — Operational Risk Intelligence Platform for Quick Commerce",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
    install_requires=[
        "pandas>=1.5",
        "numpy>=1.23",
        "streamlit>=1.30",
        "plotly>=5.15",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "pytest-cov"],
    },
    entry_points={
        "console_scripts": [
            "ivc=main:main",
            "ivc-benchmark=benchmark:run_benchmark",
        ]
    },
)
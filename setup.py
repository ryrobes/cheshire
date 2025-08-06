from setuptools import setup, find_packages
import os

# Read README for long description
def read_readme():
    with open("README.md", "r", encoding="utf-8") as f:
        return f.read()

# Read requirements
def read_requirements():
    with open("requirements.txt", "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read version from package
def read_version():
    version_file = os.path.join("cheshire", "__init__.py")
    with open(version_file) as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "0.1.0"

setup(
    name="cheshire-sql",
    version=read_version(),
    author="Cheshire Team",
    author_email="contact@example.com",
    description="Terminal-based SQL visualization tool that transforms query results into beautiful ANSI charts",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/cheshire",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Database",
        "Topic :: Scientific/Engineering :: Visualization",
        "Topic :: System :: Monitoring",
        "Topic :: Utilities",
    ],
    keywords="sql, visualization, terminal, charts, database, duckdb, cli",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cheshire=cheshire.main:main",
        ],
    },
    python_requires=">=3.8",
    include_package_data=True,
    package_data={
        "cheshire": ["*.yaml", "*.ans"],
    },
    zip_safe=False,
)
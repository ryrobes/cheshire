from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="cheshire",
    version="0.1.0",
    description="Terminal-based SQL visualization tool",
    py_modules=["cheshire"],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "cheshire=cheshire:main",
        ],
    },
    python_requires=">=3.8",
)
# Publishing to PyPI

This guide explains how to publish the Cheshire package to PyPI (Python Package Index).

## Prerequisites

1. **PyPI Account**: Create accounts at:
   - https://pypi.org (production)
   - https://test.pypi.org (for testing)

2. **Install Build Tools**:
   ```bash
   pip install --upgrade pip setuptools wheel twine build
   ```

3. **API Token**: Generate API tokens from your PyPI account settings for secure uploads.

## Pre-Publishing Checklist

### 1. Update Version Number
Edit `cheshire/__init__.py`:
```python
__version__ = "0.1.1"  # Increment appropriately
```

### 2. Update Changelog
Create or update `CHANGELOG.md` with release notes.

### 3. Verify Package Name
The package name `cheshire-sql` should be available on PyPI. Check at:
https://pypi.org/project/cheshire-sql/

If taken, update the name in:
- `setup.py`
- `pyproject.toml`

### 4. Update Project URLs
Edit `setup.py` and `pyproject.toml` to use your actual GitHub repository:
```python
url="https://github.com/yourusername/cheshire",
```

### 5. Ensure Clean Working Directory
```bash
git status  # Should be clean
git tag v0.1.0  # Tag the release
git push origin v0.1.0
```

## Building the Package

### 1. Clean Previous Builds
```bash
rm -rf build/ dist/ *.egg-info/
```

### 2. Build Distribution Files
```bash
python -m build
```

This creates:
- `dist/cheshire_sql-0.1.0-py3-none-any.whl` (wheel distribution)
- `dist/cheshire_sql-0.1.0.tar.gz` (source distribution)

### 3. Verify the Build
```bash
# Check the contents
tar -tzf dist/cheshire_sql-*.tar.gz

# Test installation in a fresh environment
python -m venv test_env
source test_env/bin/activate
pip install dist/cheshire_sql-*.whl
cheshire --version
deactivate
rm -rf test_env
```

## Publishing to Test PyPI (Recommended First)

### 1. Upload to Test PyPI
```bash
python -m twine upload --repository testpypi dist/*
```

You'll be prompted for:
- Username: `__token__`
- Password: Your test PyPI API token

### 2. Test Installation from Test PyPI
```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ cheshire-sql
```

The `--extra-index-url` ensures dependencies are pulled from regular PyPI.

### 3. Verify Functionality
```bash
cheshire --version
cheshire --help
```

## Publishing to Production PyPI

Once testing is successful:

### 1. Upload to PyPI
```bash
python -m twine upload dist/*
```

Use your production PyPI API token when prompted.

### 2. Verify on PyPI
Visit https://pypi.org/project/cheshire-sql/ to see your package.

### 3. Test Installation
```bash
pip install cheshire-sql
```

## Automating with GitHub Actions

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.x'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    
    - name: Build package
      run: python -m build
    
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Add your PyPI API token to GitHub repository secrets as `PYPI_API_TOKEN`.

## Post-Publishing

### 1. Update README
Once published, update the installation instructions in README.md:
```bash
pip install cheshire-sql
```

### 2. Create GitHub Release
Create a release on GitHub with:
- Release notes
- Changelog
- Binary distributions (optional)

### 3. Announce
Consider announcing on:
- Project website/blog
- Social media
- Relevant forums/communities

## Maintenance

### Version Updates
For subsequent releases:
1. Update version in `cheshire/__init__.py`
2. Update CHANGELOG.md
3. Commit changes
4. Tag the release: `git tag v0.1.1`
5. Build and publish

### Yanking Bad Releases
If you need to remove a bad release:
```bash
# This doesn't delete but marks as "yanked"
pip install --upgrade twine
twine yank cheshire-sql==0.1.0
```

## Troubleshooting

### Common Issues

**"Invalid distribution file"**: Ensure you're using the latest build tools:
```bash
pip install --upgrade setuptools wheel build
```

**"Package name already exists"**: Choose a different name or contact PyPI support if you own the name.

**"Invalid version"**: Follow PEP 440 versioning (e.g., 0.1.0, 0.1.0a1, 0.1.0.dev1).

**Authentication failed**: Ensure you're using API tokens, not username/password.

## Best Practices

1. **Always test on Test PyPI first**
2. **Use semantic versioning** (MAJOR.MINOR.PATCH)
3. **Keep a detailed CHANGELOG**
4. **Test in a clean environment** before publishing
5. **Use API tokens** instead of passwords
6. **Automate with CI/CD** when possible
7. **Include comprehensive documentation**
8. **Specify minimum Python version** and dependencies correctly

## Resources

- [PyPI Documentation](https://pypi.org/help/)
- [Python Packaging Guide](https://packaging.python.org/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [Semantic Versioning](https://semver.org/)
# Contributing to Resume Builder

Thank you for your interest in contributing to **Resume Builder**! We are committed to building an intelligent, sovereign, ATS-optimized career automation platform.

---

## 🛠 Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/moreganooooo/resume-builder.git
   cd resume-builder
   ```

2. **Set up Python Virtual Environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Install Pre-Commit Hooks:**
   ```bash
   pre-commit install
   ```

---

## 🧪 Running Tests & Quality Gates

Before opening a pull request, ensure all local test and lint checks pass cleanly:

```bash
# 1. Run full test suite in fast test mode
RESUME_BUILDER_TESTING=1 python -m unittest discover -s tests

# 2. Check code formatting
black --check scripts/ tests/
isort --check-only scripts/ tests/

# 3. Static analysis & security
bandit -r scripts/ -ll -q
pylint --rcfile=.pylintrc scripts/
```

---

## 📦 Submitting Pull Requests

1. Fork the repo and create your branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Write unit tests for all new modules and bug fixes.
3. Commit with concise, descriptive messages.
4. Push to your fork and submit a Pull Request using the provided PR template.

## 🎯 Description & Motivation
<!-- Provide a brief description of the changes introduced by this pull request. Link relevant issues. -->

Fixes / Closes: #

## 🛠 Type of Change
- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature (non-breaking change which adds functionality)
- [ ] ⚡ Performance optimization
- [ ] 🧹 Refactoring / Code quality cleanup
- [ ] 📚 Documentation update

## ✅ Pre-Merge Quality Checklist
- [ ] Code adheres to the repository's style and passes `black --check scripts/ tests/`
- [ ] Imports are sorted via `isort --check-only scripts/ tests/`
- [ ] Security audit passes with zero warnings via `bandit -r scripts/ -ll -q`
- [ ] Linter passes with a 10.00 / 10 rating via `pylint --rcfile=.pylintrc scripts/`
- [ ] All unit and integration tests pass cleanly via `python -m unittest discover -s tests`

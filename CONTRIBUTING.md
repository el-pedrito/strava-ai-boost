# Contributing to Strava AI Boost

Thanks for your interest! This project is a **personal-use sample** published for inspiration — it is maintained on a best-effort basis, with no SLA on issues or pull requests.

## Ways to Contribute

- **Bug reports** — open an issue with reproduction steps, expected vs actual behavior, and relevant logs (redact any secrets, account IDs, or tokens)
- **Small fixes** — typos, broken links, dependency bumps: PRs welcome
- **Larger changes** — open an issue first to discuss. Since this is a sample, features that add complexity without illustrating a new pattern may be declined

## Development Setup

```bash
git clone https://github.com/el-pedrito/strava-ai-boost.git
cd strava-ai-boost
python3.12 -m venv .venv-deploy
source .venv-deploy/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Running Tests

All tests must pass before submitting a PR:

```bash
# Backend unit tests (no AWS credentials needed)
pytest tests/unit/ -v

# Frontend tests
cd frontend && npm test

# Infrastructure tests (require AWS credentials)
export AWS_PROFILE=<your-profile>
pytest tests/ -v --ignore=tests/unit/
```

## Code Style

- **Python**: PEP 8, type hints on all function signatures, docstrings on public functions, no bare `except`, `logging` module (never `print()`)
- **TypeScript/React**: follow existing patterns in `frontend/src/`
- **CDK**: least-privilege IAM, encryption at rest, no public endpoints (see `README.md` Security section)
- See `AGENTS.md` for detailed development patterns

## Pull Request Guidelines

1. Fork the repo and create a branch from `main`
2. Keep PRs focused — one change per PR
3. Add or update tests for behavioral changes
4. Ensure `pytest tests/unit/` and `npm test` pass
5. **Never include secrets, account IDs, ARNs, or personal data** in code, tests, or commit messages

## Security Issues

Do **not** open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT-0 License](LICENSE).

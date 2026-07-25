# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.6.x   | :white_check_mark: |
| 1.5.x   | :white_check_mark: |
| < 1.5   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability within MIIE, please send an email to the project maintainer. All security vulnerabilities will be promptly addressed.

**Please do not report security vulnerabilities through public GitHub issues.**

## Disclosure Policy

When the security team receives a security bug report, they will assign it to a primary handler. This person will coordinate the fix and release process, involving the following steps:

1. Confirm the problem and determine the affected versions.
2. Audit code to find any potential similar problems.
3. Prepare fixes for all releases still under maintenance.
4. Release patches as soon as possible.

## Security Architecture

- **API authentication**: HMAC-based `X-API-Key` header comparison (timing-safe)
- **SSRF protection**: GitHub URL parser validates `github.com` host only; blocks `file://`, `gopher://`, and internal IPs
- **Path traversal prevention**: `..` and special characters rejected in repo paths; sensitive system directories blocked
- **Rate limiting**: 30 requests per minute sliding window per process
- **Docker**: Non-root user, `.dockerignore` prevents token leakage into layers
- **CI/CD**: Actions pinned to full commit SHAs; secrets never logged
- **Subprocess safety**: All `subprocess.run()` calls use list-form (no shell injection); timeouts enforced
- **Dependency hygiene**: `defusedxml` blocks XXE in XML parsing; upper bounds on all dependencies

## Security Best Practices

When using MIIE:

- Never commit API tokens or secrets to version control
- Use environment variables or `.env` files for sensitive configuration
- The `.env` file is git-ignored by default
- Set `MIIE_API_KEY` in production; without it, auth is bypassed (dev mode)
- CLI output filters sensitive information (paths, tokens, hashes)
- Run `miie doctor` to verify system health and configuration

## Verification

```bash
# Verify no secrets in codebase
grep -r "api_key\|secret\|token\|password" src/ --include="*.py"

# Verify .env is git-ignored
git check-ignore .env

# Verify Docker build excludes secrets
docker build --no-cache . 2>&1 | grep -i "secret\|token"

# Run pip-audit for known vulnerabilities
pip-audit
```

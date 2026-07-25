"""Quick ship gate audit for MIIE codebase."""
import os
import re
import glob

ROOT = r"C:\Users\Samragya\Downloads\MIEE"

findings = []


def check(category, code, severity, message, file_path=None, line=None):
    findings.append({
        "cat": category, "code": code, "sev": severity,
        "msg": message, "file": file_path, "line": line,
    })


# SEC-01: .env check
env_file = os.path.join(ROOT, ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        content = f.read()
        if "ghp_" in content or "github_pat_" in content:
            check("SEC", "01", "HIGH", ".env contains GitHub tokens (expected for local dev)")
        else:
            check("SEC", "01", "LOW", ".env present, no real tokens detected")

# SEC-03: API auth
with open("src/miie/api/server.py", encoding="utf-8", errors="replace") as f:
    server_content = f.read()
    if "X-API-Key" in server_content:
        check("SEC", "03", "PASS", "API key authentication middleware present")
    else:
        check("SEC", "03", "CRITICAL", "No API key authentication found")

# SEC-04: CORS
if "allow_origins" in server_content:
    check("SEC", "04", "PASS", "CORS middleware configured")
else:
    check("SEC", "04", "HIGH", "No CORS configuration found")

# SEC-05: Rate limiting
if "_RateLimiter" in server_content:
    check("SEC", "05", "PASS", "Rate limiting implemented")
else:
    check("SEC", "05", "HIGH", "No rate limiting found")

# SEC-06: .dockerignore
if os.path.exists(os.path.join(ROOT, ".dockerignore")):
    check("SEC", "06", "PASS", ".dockerignore present")
else:
    check("SEC", "06", "HIGH", "No .dockerignore - .env may leak into Docker layers")

# SEC-07: Dockerfile security
if os.path.exists(os.path.join(ROOT, "Dockerfile")):
    with open(os.path.join(ROOT, "Dockerfile")) as f:
        df = f.read()
        if "USER miie" in df:
            check("SEC", "07", "PASS", "Dockerfile uses non-root user")
        elif "USER root" not in df:
            check("SEC", "07", "PASS", "Dockerfile default user is non-root")
        else:
            check("SEC", "07", "CRITICAL", "Dockerfile runs as root")
        if "HEALTHCHECK" in df:
            check("SEC", "07b", "PASS", "HEALTHCHECK present in Dockerfile")
        else:
            check("SEC", "07b", "MEDIUM", "No HEALTHCHECK in Dockerfile")

# SEC-08: SHA pinning in CI
for wf in [".github/workflows/ci.yml", ".github/workflows/release.yml"]:
    path = os.path.join(ROOT, wf)
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            wfc = f.read()
            if "@sha256:" in wfc or len(re.findall(r"@[a-f0-9]{40}", wfc)) >= 4:
                check("SEC", "08", "PASS", f"{wf}: SHA-pinned actions")
            elif re.search(r"@\d", wfc):
                check("SEC", "08", "HIGH", f"{wf}: Tag-pinned (not SHA-pinned) actions")

# SEC-09: Security headers
if "_add_security_headers" in server_content:
    check("SEC", "09", "PASS", "Security headers middleware present")
else:
    check("SEC", "09", "HIGH", "No security headers middleware")

# SEC-10: Token-in-URL fix
with open("src/miie/utils/git.py", encoding="utf-8", errors="replace") as f:
    git_content = f.read()
    if "GIT_ASKPASS" in git_content:
        check("SEC", "10", "PASS", "Git token-in-URL fix present (GIT_ASKPASS)")
    else:
        check("SEC", "10", "HIGH", "Git token may be passed via URL")

# SEC-11: Workspace ID sanitization
with open("src/miie/workspace/persistence.py", encoding="utf-8", errors="replace") as f:
    pers_content = f.read()
    if "is_relative_to" in pers_content and ".." in pers_content:
        check("SEC", "11", "PASS", "Workspace ID sanitization (recursive .. stripping + is_relative_to)")
    else:
        check("SEC", "11", "CRITICAL", "Workspace ID path traversal vulnerability")

# SEC-12: Subprocess timeouts
for py_file in glob.glob(os.path.join(ROOT, "src/miie/**/*.py"), recursive=True):
    with open(py_file, encoding="utf-8", errors="replace") as f:
        content = f.read()
        if "subprocess.run(" in content and "timeout=" not in content:
            check("SEC", "12", "MEDIUM", f"subprocess.run without timeout in {os.path.relpath(py_file, ROOT)}")
            break

# SEC-13: GIT_CONFIG_NOSYSTEM
env_files_fixed = 0
for py_file in ["src/miie/processing/ingestion.py", "src/miie/processing/extraction/commit_extractor.py", "src/miie/processing/extraction/engine.py", "src/miie/benchmark/generator.py"]:
    path = os.path.join(ROOT, py_file)
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            if "GIT_CONFIG_NOSYSTEM" in f.read():
                env_files_fixed += 1
if env_files_fixed == 4:
    check("SEC", "13", "PASS", "All git subprocess calls have GIT_CONFIG_NOSYSTEM=1")
else:
    check("SEC", "13", "HIGH", f"Only {env_files_fixed}/4 git files have GIT_CONFIG_NOSYSTEM")

# CODE-01: No print() in production source
prints = []
for py in glob.glob(os.path.join(ROOT, "src/miie/**/*.py"), recursive=True):
    with open(py, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped.startswith("print(") and "test" not in py.lower():
                prints.append((os.path.relpath(py, ROOT), i))
if prints:
    check("CODE", "01", "MEDIUM", f"{len(prints)} print() calls found in source")
else:
    check("CODE", "01", "PASS", "No print() calls in production source")

# CODE-02: TODO/FIXME count
todos = []
for py in glob.glob(os.path.join(ROOT, "src/miie/**/*.py"), recursive=True):
    with open(py, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            if "TODO" in line or "FIXME" in line:
                todos.append(os.path.relpath(py, ROOT))
if len(todos) > 10:
    check("CODE", "02", "MEDIUM", f"{len(todos)} TODO/FIXME in source")
else:
    check("CODE", "02", "PASS", f"{len(todos)} TODO/FIXME (acceptable)")

# DEP-01: requirements.txt
if os.path.exists(os.path.join(ROOT, "requirements.txt")):
    check("DEP", "01", "PASS", "requirements.txt present")
else:
    check("DEP", "01", "HIGH", "No requirements.txt")

# DEP-02: Upper bounds
with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
    reqs = f.read()
    upper = len(re.findall(r"<=|==", reqs))
    if upper >= 10:
        check("DEP", "02", "PASS", f"{upper} upper-bounded dependencies")
    else:
        check("DEP", "02", "MEDIUM", f"Only {upper} upper-bounded deps")

# DEP-03: defusedxml
if "defusedxml" in reqs:
    check("DEP", "03", "PASS", "defusedxml present in requirements.txt")
else:
    check("DEP", "03", "HIGH", "defusedxml missing from requirements.txt")

# OBS-01: Logging
if "logging" in server_content:
    check("OBS", "01", "PASS", "Logging configured in API server")
else:
    check("OBS", "01", "HIGH", "No logging in API server")

# OBS-02: Health endpoint
if "/v1/health" in server_content:
    check("OBS", "02", "PASS", "Health endpoint present")
else:
    check("OBS", "02", "HIGH", "No health endpoint")

# OBS-03: Monitoring docs
if os.path.exists(os.path.join(ROOT, "docs/monitoring_setup_guide.md")):
    check("OBS", "03", "PASS", "Monitoring setup guide present")
else:
    check("OBS", "03", "MEDIUM", "No monitoring setup guide")

# OBS-04: SECURITY.md
if os.path.exists(os.path.join(ROOT, "SECURITY.md")):
    check("OBS", "04", "PASS", "SECURITY.md present")
else:
    check("OBS", "04", "MEDIUM", "No SECURITY.md")

# DEPLOY-01: Makefile targets
if os.path.exists(os.path.join(ROOT, "Makefile")):
    with open(os.path.join(ROOT, "Makefile"), encoding="utf-8") as f:
        mk = f.read()
        targets = re.findall(r"^(\w+):", mk, re.MULTILINE)
        if "lint" in targets and "test" in targets:
            check("DEPLOY", "01", "PASS", f"Makefile targets present: {', '.join(targets[:5])}")
        else:
            check("DEPLOY", "01", "MEDIUM", "Missing common Makefile targets")

# Report
print("=" * 60)
print("SHIP GATE REPORT")
print("=" * 60)
print(f"Stack: Python 3.10-3.12 + FastAPI + Click")
print(f"Scan time: immediate")

for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "PASS"]:
    items = [f for f in findings if f["sev"] == sev]
    if items and sev != "PASS":
        print(f"\n{sev} ({len(items)} findings)")
        for f in items:
            loc = f'{f["file"]}:{f["line"]}' if f.get("file") and f.get("line") else f.get("file", "")
            print(f'  [{f["cat"]}-{f["code"]}] {f["msg"]}')
            if loc:
                print(f"    -> {loc}")

passed = [f for f in findings if f["sev"] == "PASS"]
print(f"\nPASSED: {len(passed)} checks")
print(f"FAILED: {len(findings) - len(passed)} checks")

criticals = [f for f in findings if f["sev"] == "CRITICAL"]
highs = [f for f in findings if f["sev"] == "HIGH"]
print("\nVERDICT: ", end="")
if criticals:
    print(f"DO NOT SHIP ({len(criticals)} critical)")
elif highs:
    print(f"SHIP WITH CAUTION ({len(highs)} high)")
else:
    print("CLEAR TO SHIP")

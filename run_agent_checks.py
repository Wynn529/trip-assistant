"""Run offline checks and save their real output; no third-party packages needed."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    output = root / "docs" / "evidence"
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    stamp = now.strftime("%Y%m%d-%H%M%S-%f")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    commands = [
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_agent.py", "-v"],
        [sys.executable, "-B", "demo_agent.py", "--write-evidence"],
    ]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logs = [f"Executed at: {now.isoformat()}", f"Python: {platform.python_version()}", "Mode: offline"]
    success = True
    for command in commands:
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
        logs.extend(["COMMAND: " + " ".join(command), result.stdout, result.stderr, f"EXIT_CODE: {result.returncode}"])
        print(result.stdout + result.stderr)
        if result.returncode:
            success = False
            break
    log_path = output / f"agent-checks-{stamp}.log"
    log_path.write_text("\n".join(logs), encoding="utf-8")
    source_paths = [
        "travel_agent/contracts.py", "travel_agent/llm.py", "travel_agent/service.py",
        "tests/test_agent.py", "demo_agent.py", "run_agent_checks.py",
    ]
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in source_paths}
    manifest = {
        "delivery_version": "A-1.2-review", "contract_schema_version": "1.0",
        "generated_at": now.isoformat(), "python": platform.python_version(),
        "status": "passed" if success else "failed", "log": log_path.relative_to(root).as_posix(),
        "source_sha256": hashes, "real_model_test": "not tested", "real_weather_test": "not tested",
    }
    baseline = root / "前期工作.zip"
    if baseline.exists():
        manifest["baseline_archive_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
    (output / "agent-checks-latest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("检查日志：", log_path)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

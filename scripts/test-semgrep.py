"""Assert actual scanner findings against annotated positive/negative fixtures."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    fixture = ROOT / "security/semgrep-tests/patterns.py"
    expected = set()
    for number, line in enumerate(fixture.read_text().splitlines(), start=1):
        match = re.search(r"# ruleid: ([a-z-]+)", line)
        if match:
            expected.add((match.group(1), number + 1))
    result = subprocess.run(["semgrep", "scan", "--config", str(ROOT / "security/semgrep.yml"), "--json", "--jobs", "2", "--metrics=off", "--disable-version-check", str(fixture)], check=True, capture_output=True, text=True, timeout=120)
    report = json.loads(result.stdout)
    if report.get("errors"):
        raise RuntimeError("Semgrep fixture scan produced errors")
    actual = {(finding["check_id"].split(".")[-1], finding["start"]["line"]) for finding in report["results"]}
    if actual != expected or len(expected) != 5:
        raise RuntimeError(f"Rule fixtures failed. Expected {expected}; actual {actual}")
    print("Semgrep fixtures: five expected unsafe patterns found; safe examples not flagged")


if __name__ == "__main__":
    main()

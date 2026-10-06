"""GitHub control API using the user's existing Git credential manager session."""
import json
import subprocess
import urllib.request


def request(repository, endpoint, method="GET", data=None):
    credentials = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, check=True, timeout=45,
    )
    values = dict(line.split("=", 1) for line in credentials.stdout.splitlines() if "=" in line)
    token = values.get("password")
    if not token:
        raise RuntimeError("Sign into GitHub with Git Credential Manager before controlling the workflow")
    url = "https://api.github.com/repos/" + repository + "/actions/" + endpoint
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "devsecops-demo-control",
    }
    payload = None if data is None else json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=headers, method=method), timeout=45) as response:
        body = response.read()
        return json.loads(body) if body else {}


def active_runs(repository):
    page = 1
    active = []
    while True:
        runs = request(repository, f"workflows/deploy.yml/runs?per_page=100&page={page}")["workflow_runs"]
        active.extend(run for run in runs if run["status"] != "completed")
        if len(runs) < 100:
            return active
        page += 1

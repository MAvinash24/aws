"""Scanner-only fixtures: never execute these functions."""
import os
import subprocess
import requests


def shell_cases(payload):
    # ruleid: prohibit-shell-command
    subprocess.run(payload, shell=True)
    # ruleid: prohibit-shell-command
    os.system(payload)
    # ok: prohibit-shell-command
    subprocess.run(["printf", "%s", payload], check=True)


def evaluation_cases(payload):
    # ruleid: prohibit-dynamic-python
    eval(payload)
    # ruleid: prohibit-dynamic-python
    exec(payload)


def tls_cases(url):
    # ruleid: prohibit-disabled-tls
    requests.get(url, verify=False)
    # ok: prohibit-disabled-tls
    requests.get(url, timeout=10)

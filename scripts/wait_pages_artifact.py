"""Bounded wait for an uploaded Pages artifact to become visible."""
from __future__ import annotations

import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def wait_for_artifact(fetch, name, *, attempts=12, delay=5, settle=10, sleep=time.sleep):
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(1, attempts + 1):
        matches = [a for a in fetch() if a.get("name") == name and not a.get("expired")]
        if len(matches) > 1:
            raise RuntimeError(f"Multiple active artifacts named {name}")
        if len(matches) == 1:
            artifact = matches[0]
            if not artifact.get("id") or not artifact.get("size_in_bytes", 0):
                raise RuntimeError(f"Artifact {name} has invalid metadata")
            print(f"Artifact {name} is visible (id={artifact['id']}); settling before deployment.", flush=True)
            sleep(settle)
            return artifact
        print(f"Artifact {name} not yet visible ({attempt}/{attempts})", flush=True)
        if attempt < attempts:
            sleep(delay)
    raise TimeoutError(f"Artifact {name} did not become visible")


def main():
    base = os.environ["GITHUB_API_URL"]
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ["GITHUB_RUN_ID"]
    name = os.environ["PAGES_ARTIFACT_NAME"]
    query = urlencode({"name": name, "per_page": 100})
    url = f"{base}/repos/{repo}/actions/runs/{run}/artifacts?{query}"

    def fetch():
        req = Request(url, headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "os29-pages-artifact-wait",
        })
        with urlopen(req, timeout=15) as response:
            payload = json.load(response)
        artifacts = payload["artifacts"]
        if payload.get("total_count", len(artifacts)) > len(artifacts):
            raise RuntimeError("Artifact response exceeded one page")
        return artifacts

    wait_for_artifact(fetch, name)


if __name__ == "__main__":
    main()

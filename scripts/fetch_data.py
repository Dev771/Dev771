#!/usr/bin/env python3
"""Fetch the numbers the profile cards show and save them under data/.

    data/contributions.json  one entry per day for the last year
    data/repos.json          stars, language and dates for the repos in profile.json

Needs a GitHub token in GITHUB_TOKEN (the Actions token is enough). Locally it
falls back to `gh auth token`.
"""
import datetime as dt
import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"


def token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def graphql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token()}", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.load(res)
    if body.get("errors"):
        raise SystemExit(f"GitHub GraphQL error: {body['errors']}")
    return body["data"]


REPO_FIELDS = """
  name url homepageUrl stargazerCount forkCount pushedAt
  primaryLanguage { name color }
  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { nodes { name color } }
"""


def main():
    login = PROFILE["login"]
    repo_parts = "\n".join(
        f'r{i}: repository(owner: $login, name: {json.dumps(r["name"])}) {{ {REPO_FIELDS} }}'
        for i, r in enumerate(PROFILE["repos"])
    )
    query = f"""
    query($login: String!) {{
      user(login: $login) {{
        contributionsCollection {{
          contributionCalendar {{
            totalContributions
            weeks {{ contributionDays {{ date contributionCount }} }}
          }}
        }}
      }}
      {repo_parts}
    }}"""
    data = graphql(query, {"login": login})

    cal = data["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    DATA.mkdir(exist_ok=True)
    (DATA / "contributions.json").write_text(
        json.dumps({"fetched_at": now, "total": cal["totalContributions"], "days": days}, indent=1),
        encoding="utf-8",
    )

    repos = {}
    for i, r in enumerate(PROFILE["repos"]):
        node = data[f"r{i}"]
        if node is None:
            raise SystemExit(f"Repo not found: {login}/{r['name']}")
        repos[r["name"]] = {
            "url": node["url"],
            "homepage": node["homepageUrl"] or None,
            "stars": node["stargazerCount"],
            "forks": node["forkCount"],
            "pushed_at": node["pushedAt"],
            "language": node["primaryLanguage"],
            "languages": node["languages"]["nodes"],
        }
    (DATA / "repos.json").write_text(json.dumps(repos, indent=1), encoding="utf-8")
    print(f"{len(days)} days, {cal['totalContributions']} contributions, {len(repos)} repos")


if __name__ == "__main__":
    main()

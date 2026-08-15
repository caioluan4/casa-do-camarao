#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://casadocamarao.goatcounter.com/api/v0"
HITS_LIMIT = 100
GITHUB_API = "https://api.github.com"

# GoatCounter tracking went live in August 2026; there's no data before
# this, so it's a safe (and cheap) lower bound for the daily history.
ALL_TIME_START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def api_get(path, params=None):
    api_key = os.environ.get("GOATCOUNTER_API_KEY")
    if not api_key:
        print("Erro: variável de ambiente GOATCOUNTER_API_KEY não definida.", file=sys.stderr)
        sys.exit(1)

    url = f"{API_BASE}{path}"
    query = urlencode(params or {}, doseq=True)
    if query:
        url = f"{url}?{query}"

    request = Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Erro HTTP {e.code} ao chamar {url}:\n{body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Erro de rede ao chamar {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def fetch_hits_with_daily_breakdown(start):
    hits = []
    exclude_paths = []
    while True:
        params = {"limit": HITS_LIMIT, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "group": "day"}
        if exclude_paths:
            params["exclude_paths"] = exclude_paths
        data = api_get("/stats/hits", params)
        page_hits = data.get("hits", [])
        hits.extend(page_hits)
        exclude_paths.extend(str(h["path_id"]) for h in page_hits)
        if not data.get("more") or not page_hits:
            break
    return hits


def build_items(hits):
    items = []
    for hit in hits:
        days = {}
        for entry in hit.get("stats", []):
            day = entry.get("day")
            if day:
                days[day[:10]] = entry.get("daily", 0)
        items.append({
            "path": hit.get("path", ""),
            "title": hit.get("title", ""),
            # GoatCounter itself flags each hit as a page view or a click
            # event (event=true), more reliable than guessing from the path.
            "event": bool(hit.get("event")),
            "days": days,
        })
    return items


def update_gist(stats):
    gist_id = os.environ.get("GIST_ID")
    gh_token = os.environ.get("GH_TOKEN")
    if not gist_id:
        print("Erro: variável de ambiente GIST_ID não definida.", file=sys.stderr)
        sys.exit(1)
    if not gh_token:
        print("Erro: variável de ambiente GH_TOKEN não definida.", file=sys.stderr)
        sys.exit(1)

    content = json.dumps(stats, ensure_ascii=False, indent=2)
    body = json.dumps({"files": {"stats.json": {"content": content}}}).encode("utf-8")

    url = f"{GITHUB_API}/gists/{gist_id}"
    request = Request(url, data=body, method="PATCH", headers={
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "casa-do-camarao-stats-bot",
        "Content-Type": "application/json",
    })

    try:
        with urlopen(request, timeout=30) as response:
            response.read()
    except HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        print(f"Erro HTTP {e.code} ao atualizar o Gist:\n{body_err}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Erro de rede ao atualizar o Gist: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    now = datetime.now(timezone.utc)
    hits = fetch_hits_with_daily_breakdown(ALL_TIME_START)
    items = build_items(hits)

    stats = {
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
    }

    update_gist(stats)

    pages = sum(1 for i in items if not i["event"])
    events = sum(1 for i in items if i["event"])
    print(f"Gist atualizado: {pages} páginas, {events} eventos, com histórico diário completo.")


if __name__ == "__main__":
    main()

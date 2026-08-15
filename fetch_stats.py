#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://casadocamarao.goatcounter.com/api/v0"
EVENT_PREFIXES = ("clique-", "lp-clique-")
HITS_LIMIT = 100
# /stats/total and /stats/hits default to the last 7 days when no start/end
# is given; use a far-past start so the numbers reflect all-time totals.
ALL_TIME_START = "2000-01-01T00:00:00Z"

GITHUB_API = "https://api.github.com"


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


def fetch_total_visits():
    data = api_get("/stats/total", {"start": ALL_TIME_START})
    return data.get("total", 0)


def fetch_all_hits():
    hits = []
    exclude_paths = []
    while True:
        params = {"limit": HITS_LIMIT, "start": ALL_TIME_START}
        if exclude_paths:
            params["exclude_paths"] = exclude_paths
        data = api_get("/stats/hits", params)
        page_hits = data.get("hits", [])
        hits.extend(page_hits)
        exclude_paths.extend(str(h["path_id"]) for h in page_hits)
        if not data.get("more") or not page_hits:
            break
    return hits


def classify_hits(hits):
    pages, events = [], []
    for hit in hits:
        path = hit.get("path", "")
        item = {
            "path": path,
            "title": hit.get("title", ""),
            "count": hit.get("count", 0),
        }
        target = events if path.startswith(EVENT_PREFIXES) else pages
        target.append(item)

    pages.sort(key=lambda x: x["count"], reverse=True)
    events.sort(key=lambda x: x["count"], reverse=True)
    return pages, events


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
    visits = fetch_total_visits()
    hits = fetch_all_hits()
    pages, events = classify_hits(hits)

    stats = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": {"visits": visits},
        "pages": pages,
        "events": events,
    }

    update_gist(stats)

    print(f"Gist atualizado: {visits} visitas totais, {len(pages)} páginas, {len(events)} eventos.")


if __name__ == "__main__":
    main()

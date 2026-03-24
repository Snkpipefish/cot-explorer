"""
signal_server.py — Flask-server for signaler og GitHub-innholdsoppdatering
Endepunkter:
  GET  /status          — helsesjekk
  POST /upload          — last opp signal-JSON (X-API-Key påkrevd)
  GET  /signals         — hent lagret signal-JSON
  POST /update-content  — oppdater tekst på GitHub-hostet nettside (X-API-Key påkrevd)
  GET  /content-status  — vis siste commit-info
"""

import os
import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from github import Github, GithubException

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Konfigurasjon ─────────────────────────────────────────
API_KEY       = os.environ.get("SCALP_API_KEY", "")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")          # "brukernavn/repo-navn"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

if not API_KEY:
    log.warning("SCALP_API_KEY ikke satt — alle forespørsler vil bli avvist")

# ── State (in-memory) ─────────────────────────────────────
_signals_store: dict = {}
_content_status: dict = {
    "last_update":  None,
    "last_commit":  None,
    "repo":         GITHUB_REPO,
    "branch":       GITHUB_BRANCH,
}

app = Flask(__name__)

# ── Auth-decorator ────────────────────────────────────────
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if not API_KEY or key != API_KEY:
            log.warning("Ugyldig API-nøkkel fra %s", request.remote_addr)
            return jsonify({"error": "Ugyldig eller manglende X-API-Key"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Eksisterende endepunkter ──────────────────────────────

@app.route("/status", methods=["GET"])
def status():
    log.info("GET /status")
    return jsonify({
        "status":  "ok",
        "time":    datetime.now(timezone.utc).isoformat(),
        "signals": len(_signals_store),
    })


@app.route("/upload", methods=["POST"])
@require_api_key
def upload():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Body må være gyldig JSON"}), 400
    _signals_store.update(data)
    log.info("POST /upload — %d nøkler mottatt", len(data))
    return jsonify({"status": "ok", "keys_stored": len(_signals_store)})


@app.route("/signals", methods=["GET"])
def signals():
    log.info("GET /signals")
    return jsonify(_signals_store)

# ── Nye endepunkter ───────────────────────────────────────

@app.route("/update-content", methods=["POST"])
@require_api_key
def update_content():
    """
    Oppdater tekst i HTML-filer i GitHub-repoet.
    Body:
      {
        "updates": [
          {"file": "index.html", "selector": "#hero-title", "content": "Ny tekst"},
          ...
        ],
        "commit_message": "Valgfri commit-melding"
      }
    """
    if not GITHUB_TOKEN:
        log.error("/update-content: GITHUB_TOKEN ikke satt")
        return jsonify({"error": "GITHUB_TOKEN ikke konfigurert på serveren"}), 500
    if not GITHUB_REPO:
        log.error("/update-content: GITHUB_REPO ikke satt")
        return jsonify({"error": "GITHUB_REPO ikke konfigurert på serveren"}), 500

    body = request.get_json(silent=True)
    if not body or "updates" not in body:
        return jsonify({"error": "Body må inneholde 'updates'-liste"}), 400

    updates    = body["updates"]
    commit_msg = body.get("commit_message") or f"Auto-oppdatering {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    if not isinstance(updates, list) or len(updates) == 0:
        return jsonify({"error": "'updates' må være en ikke-tom liste"}), 400

    for i, u in enumerate(updates):
        for key in ("file", "selector", "content"):
            if key not in u:
                return jsonify({"error": f"updates[{i}] mangler feltet '{key}'"}), 400

    log.info("POST /update-content — %d endringer, repo=%s branch=%s",
             len(updates), GITHUB_REPO, GITHUB_BRANCH)

    try:
        gh   = Github(GITHUB_TOKEN)
        repo = gh.get_repo(GITHUB_REPO)
    except GithubException as e:
        log.error("GitHub-autentisering feilet: %s", e)
        return jsonify({"error": f"GitHub-tilkobling feilet: {e.data.get('message', str(e))}"}), 502

    # Grupper updates etter fil for å unngå flere commits per fil
    files_to_update: dict = {}
    for u in updates:
        files_to_update.setdefault(u["file"], []).append(u)

    changed_files = []
    errors        = []

    for filename, file_updates in files_to_update.items():
        try:
            gh_file    = repo.get_contents(filename, ref=GITHUB_BRANCH)
            html_bytes = gh_file.decoded_content
            soup       = BeautifulSoup(html_bytes, "html.parser")

            modified = False
            for u in file_updates:
                selector = u["selector"]
                new_text = u["content"]

                element = _find_element(soup, selector)
                if element is None:
                    errors.append(f"{filename}: fant ikke element '{selector}'")
                    log.warning("Fant ikke '%s' i %s", selector, filename)
                    continue

                # Bytt ut bare tekstinnholdet — behold attributter og struktur
                element.string = new_text
                modified = True
                log.info("  %s [%s] → '%s'", filename, selector, new_text[:60])

            if not modified:
                continue

            new_content = str(soup)
            repo.update_file(
                path    = filename,
                message = commit_msg,
                content = new_content,
                sha     = gh_file.sha,
                branch  = GITHUB_BRANCH,
            )
            changed_files.append(filename)
            log.info("  Committed %s → %s (%s)", filename, GITHUB_BRANCH, commit_msg)

        except GithubException as e:
            msg = e.data.get("message", str(e)) if hasattr(e, "data") else str(e)
            log.error("GitHub-feil for %s: %s", filename, msg)
            errors.append(f"{filename}: GitHub-feil — {msg}")
        except Exception as e:
            log.error("Uventet feil for %s: %s", filename, e)
            errors.append(f"{filename}: {e}")

    if changed_files:
        _content_status["last_update"] = datetime.now(timezone.utc).isoformat()
        _content_status["last_commit"] = commit_msg
        _content_status["repo"]        = GITHUB_REPO
        _content_status["branch"]      = GITHUB_BRANCH

    status_code = 200 if changed_files else 422
    return jsonify({
        "status":         "ok" if changed_files else "ingen_endringer",
        "changed_files":  changed_files,
        "commit_message": commit_msg,
        "errors":         errors,
    }), status_code


@app.route("/content-status", methods=["GET"])
def content_status():
    log.info("GET /content-status")
    return jsonify(_content_status)


# ── Hjelpefunksjon: CSS-selektor → BeautifulSoup-element ─
def _find_element(soup, selector: str):
    """
    Enkel CSS-selektor-parser:
      #id       → find(id=...)
      .klasse   → find(class_=...)
      tagnavn   → find(tagnavn)
    Komplekse selektorer delegeres til soup.select_one().
    """
    selector = selector.strip()
    if selector.startswith("#"):
        return soup.find(id=selector[1:])
    if selector.startswith("."):
        return soup.find(class_=selector[1:])
    try:
        return soup.select_one(selector)
    except Exception:
        return soup.find(selector)


# ── Oppstart ──────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("Starter signal_server på port %d", port)
    log.info("  GITHUB_REPO   = %s", GITHUB_REPO or "(ikke satt)")
    log.info("  GITHUB_BRANCH = %s", GITHUB_BRANCH)
    log.info("  API_KEY satt  = %s", bool(API_KEY))
    app.run(host="0.0.0.0", port=port, debug=False)

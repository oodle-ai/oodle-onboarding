"""Swiggy MCP OAuth 2.1 + PKCE authentication helper.

Performs Dynamic Client Registration and PKCE authorization
against Swiggy's OAuth endpoints. Opens a browser for phone+OTP
login and writes the access token to .env.

Uses only Python stdlib (no pip install needed).

Usage:
    python auth.py
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from typing import Optional

SWIGGY_MCP_BASE = "https://mcp.swiggy.com"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
SCOPES = "mcp:tools mcp:resources mcp:prompts"

_auth_code = None  # type: Optional[str]
_auth_error = None  # type: Optional[str]
_server_done = threading.Event()


def _http_get_json(url: str) -> dict:
    """GET a URL and parse the JSON response."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return json.loads(resp.read())


def _http_post_json(url: str, payload: dict) -> dict:
    """POST JSON to a URL and parse the JSON response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return json.loads(resp.read())


def _http_post_form(url: str, payload: dict) -> dict:
    """POST form-encoded data to a URL and parse the JSON response."""
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return json.loads(resp.read())


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth redirect callback on localhost."""

    def do_GET(self):
        global _auth_code, _auth_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self._respond("Authentication successful! You can close this tab.")
        elif "error" in params:
            _auth_error = params.get("error_description", params["error"])[0]
            self._respond(f"Authentication failed: {_auth_error}")
        else:
            self._respond("Unknown callback response.", status=400)

        _server_done.set()

    def _respond(self, message: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = f"<html><body><h2>{message}</h2></body></html>"
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass


def _generate_pkce():
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _discover_oauth_endpoints():
    """Discover authorization and token endpoints from Swiggy's well-known URLs."""
    print("Discovering OAuth endpoints...")
    resource_url = f"{SWIGGY_MCP_BASE}/food/.well-known/oauth-protected-resource"
    resource_meta = _http_get_json(resource_url)

    auth_server_url = resource_meta.get(
        "authorization_servers", [f"{SWIGGY_MCP_BASE}/auth"]
    )[0]

    return {
        "authorization_endpoint": f"{auth_server_url}/authorize",
        "token_endpoint": f"{auth_server_url}/token",
        "registration_endpoint": f"{auth_server_url}/register",
    }


def _register_client(registration_endpoint: str) -> dict:
    """Perform Dynamic Client Registration."""
    print("Registering OAuth client...")
    payload = {
        "client_name": "Swiggy Builders Demo (localhost)",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    return _http_post_json(registration_endpoint, payload)


def _exchange_code(token_endpoint: str, code: str, verifier: str, client_id: str) -> dict:
    """Exchange authorization code for access token."""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    return _http_post_form(token_endpoint, payload)


def _write_token_to_env(token: str):
    """Write SWIGGY_ACCESS_TOKEN to .env file."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.abspath(env_path)

    lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        if line.startswith("SWIGGY_ACCESS_TOKEN="):
            lines[i] = f"SWIGGY_ACCESS_TOKEN={token}\n"
            found = True
            break

    if not found:
        lines.append(f"SWIGGY_ACCESS_TOKEN={token}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    print(f"Token written to {env_path}")


def authenticate():
    """Run the full OAuth 2.1 + PKCE flow."""
    global _auth_code, _auth_error

    endpoints = _discover_oauth_endpoints()

    if not endpoints.get("registration_endpoint"):
        print("ERROR: No registration endpoint found. Cannot proceed.")
        sys.exit(1)

    client_info = _register_client(endpoints["registration_endpoint"])
    client_id = client_info["client_id"]
    print(f"Registered client: {client_id}")

    verifier, challenge = _generate_pkce()

    state = secrets.token_urlsafe(32)

    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"{endpoints['authorization_endpoint']}?{auth_params}"

    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print(f"\nOpening browser for Swiggy login...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for callback...")
    _server_done.wait(timeout=300)
    server.shutdown()

    if _auth_error:
        print(f"ERROR: {_auth_error}")
        sys.exit(1)

    if not _auth_code:
        print("ERROR: No authorization code received (timeout?).")
        sys.exit(1)

    print("Exchanging code for token...")
    token_resp = _exchange_code(
        endpoints["token_endpoint"], _auth_code, verifier, client_id
    )

    access_token = token_resp["access_token"]
    expires_in = token_resp.get("expires_in", "unknown")
    print(f"Access token obtained (expires in {expires_in}s)")

    _write_token_to_env(access_token)
    print("\nDone! Run `make up` to start the demo.")


if __name__ == "__main__":
    authenticate()

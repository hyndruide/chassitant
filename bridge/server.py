"""Chassitant Bridge HTTP Server.

Lightweight, zero-dependency server connecting Home Assistant to Antigravity CLI (agy).
"""

import json
import logging
import os
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Ensure local imports work regardless of execution directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.agy_client import AgyClient
from bridge.auth_manager import AuthManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("chassitant.server")


class ChassitantRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Chassitant Bridge."""

    server_version = "ChassitantBridge/1.0"

    @property
    def auth_manager(self) -> AuthManager:
        return self.server.auth_manager  # type: ignore

    @property
    def agy_client(self) -> AgyClient:
        return self.server.agy_client  # type: ignore

    def send_json(self, status: int, data: Dict[str, Any]) -> None:
        """Send JSON response with CORS headers."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def check_authorization(self) -> bool:
        """Validate Bearer token in Authorization header."""
        auth_header = self.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()

        client_ip = self.client_address[0]
        is_local = (
            client_ip in ("127.0.0.1", "::1", "localhost")
            or client_ip.startswith("172.30.")
            or client_ip.startswith("172.17.")
        )

        if not self.auth_manager.validate_token(token):
            if is_local:
                return True
            self.send_json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "success": False,
                    "error": "Jeton d'authentification invalide ou manquant (Unauthorized)",
                },
            )
            return False
        return True

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = urlparse(self.path).path

        # Health / Status check (public or protected)
        if path in ("/", "/api/status", "/api/health"):
            if not self.check_authorization():
                return

            auth_ok, auth_msg = self.agy_client.check_auth(timeout=10)
            mcp_servers = self.agy_client.list_mcp_servers()
            models = self.agy_client.list_models()

            self.send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "bridge_version": "1.0.0",
                    "agy_binary": self.agy_client.binary_path,
                    "agy_installed": self.agy_client.is_installed(),
                    "agy_authenticated": auth_ok,
                    "agy_status_message": auth_msg,
                    "mcp_servers": mcp_servers,
                    "models_count": len(models),
                },
            )
            return

        # List models endpoint
        if path == "/api/models":
            if not self.check_authorization():
                return
            models = self.agy_client.list_models()
            self.send_json(HTTPStatus.OK, {"success": True, "models": models})
            return

        self.send_json(
            HTTPStatus.NOT_FOUND,
            {"success": False, "error": f"Endpoint inconnu : {path}"},
        )

    def do_POST(self) -> None:
        """Handle POST requests."""
        path = urlparse(self.path).path

        # Endpoint to check auth token
        if path in ("/api/auth/check", "/api/auth/verify"):
            if not self.check_authorization():
                return
            auth_ok, auth_msg = self.agy_client.check_auth(timeout=10)
            self.send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "valid": True,
                    "agy_authenticated": auth_ok,
                    "message": auth_msg,
                },
            )
            return

        # Main processing endpoint
        if path in ("/api/process", "/api/chat"):
            if not self.check_authorization():
                return

            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": "Corps de requête vide"},
                )
                return

            try:
                raw_body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(raw_body)
            except Exception as err:
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": f"JSON invalide : {err}"},
                )
                return

            prompt = payload.get("prompt", "")
            if not prompt or not isinstance(prompt, str):
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": "Le paramètre 'prompt' est obligatoire."},
                )
                return

            conversation_id = payload.get("conversation_id")
            model = payload.get("model")
            effort = payload.get("effort")
            dangerously_skip_permissions = payload.get(
                "dangerously_skip_permissions", True
            )
            timeout = int(payload.get("timeout", 60))

            logger.info(
                "Traitement de la requête: prompt='%s...' (conv_id=%s)",
                prompt[:40],
                conversation_id,
            )

            result = self.agy_client.process(
                prompt=prompt,
                conversation_id=conversation_id,
                model=model,
                effort=effort,
                dangerously_skip_permissions=dangerously_skip_permissions,
                timeout=timeout,
            )

            status_code = HTTPStatus.OK if result.get("success") else HTTPStatus.INTERNAL_SERVER_ERROR
            self.send_json(status_code, result)
            return

        self.send_json(
            HTTPStatus.NOT_FOUND,
            {"success": False, "error": f"Endpoint inconnu : {path}"},
        )

    def log_message(self, format: str, *args: Any) -> None:
        """Custom HTTP request logger."""
        logger.info("%s - %s", self.address_string(), format % args)


class ChassitantBridgeServer(ThreadingHTTPServer):
    """Threaded HTTP Server carrying auth and agy client state."""

    def __init__(
        self,
        server_address: tuple[str, int],
        auth_manager: AuthManager,
        agy_client: AgyClient,
    ) -> None:
        super().__init__(server_address, ChassitantRequestHandler)
        self.auth_manager = auth_manager
        self.agy_client = agy_client


def get_local_ip_addresses() -> List[str]:
    """Retrieve non-loopback local IPv4 addresses."""
    ips = []
    try:
        hostname = socket.gethostname()
        _, _, host_ips = socket.gethostbyname_ex(hostname)
        for ip in host_ips:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        ips.append("127.0.0.1")
    return ips


def main() -> None:
    """Entry point for the Chassitant Bridge server."""
    auth_mgr = AuthManager()
    agy_cli = AgyClient()

    config = auth_mgr.config
    host = config.get("host", "0.0.0.0")
    port = int(config.get("port", 8099))
    api_key = auth_mgr.get_api_key()

    print("=" * 68, flush=True)
    print(" 🌟 CHASSITANT - PASSERELLE ANTIGRAVITY (AGY) POUR HOME ASSISTANT 🌟", flush=True)
    print("=" * 68, flush=True)

    # 1. Verification binaire agy
    if not agy_cli.is_installed():
        print("\n❌ ERREUR : Le binaire 'agy' est introuvable sur votre système !", flush=True)
        print("Veuillez installer Antigravity CLI ou vous assurer qu'il est dans le PATH.", flush=True)
        print("Emplacements vérifiés : PATH, ~/.local/bin, ~/AppData/Local/agy/bin", flush=True)
        sys.exit(1)

    print(f"✅ Binaire agy détecté : {agy_cli.binary_path}", flush=True)

    # 2. Vérification authentification Google Antigravity
    print("🔍 Vérification de la session Google Antigravity...", flush=True)
    auth_ok, auth_msg = agy_cli.check_auth(timeout=10)

    if not auth_ok:
        print(f"\n⚠️  {auth_msg}", flush=True)
        if sys.stdin.isatty():
            print("👉 Lancement de la procédure de connexion Google...", flush=True)
            login_success = agy_cli.trigger_interactive_login()
            if not login_success:
                print("\n❌ Échec de l'authentification Google. Relancez le script pour réessayer.", flush=True)
                sys.exit(1)
            auth_ok, auth_msg = agy_cli.check_auth(timeout=10)
        else:
            print("ℹ️ Mode arrière-plan : connectez-vous via le terminal Ingress dans Home Assistant.", flush=True)
    else:
        print("✅ Authentification Google active et prête !", flush=True)

    # 3. Informations MCP
    mcps = agy_cli.list_mcp_servers()
    if mcps:
        print(f"🔌 Serveurs MCP connectés ({len(mcps)}) :", flush=True)
        for m in mcps:
            print(f"   • {m.get('name')} ({m.get('status')}) -> {m.get('target', '')[:45]}", flush=True)
    else:
        print("ℹ️ Aucun serveur MCP configuré dans agy (ou détection désactivée).", flush=True)

    # 4. Affichage des coordonnées de connexion
    local_ips = get_local_ip_addresses()
    primary_ip = local_ips[0] if local_ips else "127.0.0.1"

    print("\n" + "-" * 68, flush=True)
    print("🚀 LE SERVEUR BRIDGE EST EN COURS D'EXÉCUTION !", flush=True)
    print("-" * 68, flush=True)
    print("À renseigner dans Home Assistant (Ajouter intégration > Chassitant) :", flush=True)
    print(f"  • Hôte / IP :  {primary_ip}", flush=True)
    print(f"  • Port      :  {port}", flush=True)
    print(f"  • Jeton API :  {api_key}", flush=True)
    print(f"\nToutes les adresses IP disponibles :", flush=True)
    for ip in local_ips:
        print(f"  - http://{ip}:{port}", flush=True)
    print("-" * 68, flush=True)
    print("Appuyez sur Ctrl+C pour arrêter le serveur.\n", flush=True)

    server = ChassitantBridgeServer((host, port), auth_mgr, agy_cli)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur Chassitant Bridge...")
        server.server_close()
        sys.exit(0)


if __name__ == "__main__":
    main()

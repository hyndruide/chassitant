"""Chassitant Bridge & Chatbot Server.

Multi-threaded HTTP server providing:
- Ingress Web UI (Chatbot with Collapsible Drawer, Multi-Conversations, Auth & MCP manager)
- REST API for conversations and prompts
- Direct API endpoint for Home Assistant Assist (/api/process)
"""

import json
import logging
import mimetypes
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import queue
from bridge.agy_client import AgyClient
from bridge.auth_manager import AuthManager
from bridge.conversation_store import ConversationStore
from bridge.mcp_manager import McpManager
from bridge.turn_manager import ActiveTurn, TurnManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("chassitant.server")


class ChassitantRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Chassitant Web UI & Bridge API."""

    server_version = "Chassitant/1.1"

    @property
    def auth_manager(self) -> AuthManager:
        return self.server.auth_manager  # type: ignore

    @property
    def agy_client(self) -> AgyClient:
        return self.server.agy_client  # type: ignore

    @property
    def conv_store(self) -> ConversationStore:
        return self.server.conv_store  # type: ignore

    @property
    def mcp_manager(self) -> McpManager:
        return self.server.mcp_manager  # type: ignore

    @property
    def turn_manager(self) -> TurnManager:
        return self.server.turn_manager  # type: ignore

    def send_json(self, status: int, data: Dict[str, Any]) -> None:
        """Send JSON response with CORS headers."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def check_authorization(self) -> bool:
        """Validate Bearer token with local access exemption."""
        client_ip = self.client_address[0]
        # Ingress and local container network calls are trusted
        is_local = (
            client_ip in ("127.0.0.1", "::1", "localhost")
            or client_ip.startswith("172.30.")
            or client_ip.startswith("172.17.")
        )

        auth_header = self.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()

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

    def read_json_body(self) -> Optional[Dict[str, Any]]:
        """Parse request body as JSON."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        try:
            raw = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw)
        except Exception as err:
            logger.warning("Failed parsing JSON body: %s", err)
            return None

    def get_clean_path(self) -> str:
        """Strip X-Ingress-Path or /api/hassio_ingress/ prefix if present."""
        path = urlparse(self.path).path
        ingress_path = self.headers.get("X-Ingress-Path", "").rstrip("/")
        if ingress_path and path.startswith(ingress_path):
            path = path[len(ingress_path):]
        elif "/api/hassio_ingress/" in path:
            parts = path.split("/api/hassio_ingress/")
            if len(parts) > 1:
                token_and_rest = parts[1].split("/", 1)
                path = "/" + token_and_rest[1] if len(token_and_rest) > 1 else "/"
        return path if path else "/"

    def stream_turn_sse(self, turn: ActiveTurn) -> None:
        """Stream live turn events to an SSE client."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.flush()
        except Exception:
            pass

        q = turn.subscribe()
        try:
            while True:
                try:
                    event = q.get(timeout=1.0)
                except queue.Empty:
                    if turn.status != "running":
                        break
                    # Keep-alive comment for reverse-proxies
                    try:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                    except Exception:
                        break
                    continue

                try:
                    line = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    # Client disconnected, but background worker keeps running!
                    break

                if event.get("type") in ("finished", "error"):
                    break
        finally:
            turn.unsubscribe(q)

    def serve_static(self, rel_path: str) -> bool:
        """Serve static files for the Ingress web UI."""
        web_dir: Path = self.server.web_dir  # type: ignore
        if not web_dir.is_dir():
            return False

        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")

        clean_path = (web_dir / rel_path).resolve()
        if not clean_path.is_file() or not str(clean_path).startswith(str(web_dir.resolve())):
            # If not found directly, try index.html for SPA routing
            clean_path = (web_dir / "index.html").resolve()
            if not clean_path.is_file():
                return False

        content_type, _ = mimetypes.guess_type(str(clean_path))
        content_type = content_type or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"

        try:
            with open(clean_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return True
        except Exception as err:
            logger.warning("Error serving static %s: %s", clean_path, err)
            return False

    def proxy_terminal(self) -> None:
        """Reverse-proxy HTTP and WebSocket requests to ttyd on port 8097."""
        backend_host = "127.0.0.1"
        backend_port = 8097
        clean_path = self.get_clean_path()
        if "?" in self.path:
            query = self.path.split("?", 1)[1]
            clean_path = f"{clean_path}?{query}"

        is_ws = (self.headers.get("Upgrade", "").lower() == "websocket")

        if is_ws:
            try:
                backend_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                backend_sock.connect((backend_host, backend_port))

                backend_requestline = f"{self.command} {clean_path} HTTP/1.1\r\n".encode("latin-1")
                headers_list = []
                for k, v in self.headers.items():
                    if k.lower() == "host":
                        headers_list.append(b"Host: 127.0.0.1:8097\r\n")
                    else:
                        headers_list.append(f"{k}: {v}\r\n".encode("latin-1"))
                backend_sock.sendall(backend_requestline + b"".join(headers_list) + b"\r\n")

                client_sock = self.connection

                def forward(src: socket.socket, dst: socket.socket) -> None:
                    try:
                        while True:
                            data = src.recv(4096)
                            if not data:
                                break
                            dst.sendall(data)
                    except Exception:
                        pass
                    finally:
                        try:
                            dst.close()
                        except Exception:
                            pass

                t1 = threading.Thread(target=forward, args=(client_sock, backend_sock), daemon=True)
                t2 = threading.Thread(target=forward, args=(backend_sock, client_sock), daemon=True)
                t1.start()
                t2.start()
                t1.join()
                t2.join()
                self.close_connection = True
            except Exception as err:
                logger.error("Terminal WebSocket proxy error: %s", err)
            return

        # Normal HTTP proxy for ttyd HTML, JS, CSS, token
        try:
            backend_url = f"http://{backend_host}:{backend_port}{clean_path}"
            headers_dict = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
            body = None
            if self.command == "POST":
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len > 0 else None

            req = urllib.request.Request(backend_url, data=body, headers=headers_dict, method=self.command)
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.send_response(resp.status)
                for h, v in resp.getheaders():
                    if h.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(h, v)
                data = resp.read()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as err:
            self.send_response(err.code)
            for h, v in err.headers.items():
                if h.lower() not in ("transfer-encoding", "content-length"):
                    self.send_header(h, v)
            err_body = err.read()
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as err:
            logger.warning("Terminal proxy error for %s: %s", clean_path, err)
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": f"Terminal Ingress non disponible ({err})"})

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.get_clean_path()

        # Terminal proxy route
        if path.startswith("/terminal"):
            self.proxy_terminal()
            return

        # 1. API Conversations list
        if path == "/api/conversations":
            if not self.check_authorization():
                return
            convs = self.conv_store.list_conversations()
            self.send_json(HTTPStatus.OK, {"success": True, "conversations": convs})
            return

        # 2. API Single Conversation & Stream Reconnection
        if path.startswith("/api/conversations/"):
            if not self.check_authorization():
                return
            clean_sub = path.replace("/api/conversations/", "").strip()

            # Live Stream Reconnection endpoint
            if clean_sub.endswith("/stream"):
                conv_id = clean_sub.replace("/stream", "").strip()
                turn = self.turn_manager.get_turn(conv_id)
                if not turn:
                    self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": "Aucune tâche en cours pour cette discussion"})
                    return
                self.stream_turn_sse(turn)
                return

            conv_id = clean_sub
            conv = self.conv_store.get_conversation(conv_id)
            if conv:
                conv_copy = dict(conv)
                turn = self.turn_manager.get_turn(conv_id)
                if turn:
                    conv_copy["active_turn"] = turn.get_snapshot()
                self.send_json(HTTPStatus.OK, {"success": True, "conversation": conv_copy})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": "Conversation introuvable"})
            return

        # 3. Status endpoint
        if path in ("/api/status", "/api/health"):
            if not self.check_authorization():
                return
            auth_ok, auth_msg = self.agy_client.check_auth(timeout=5)
            mcps = self.mcp_manager.list_mcp_servers()
            models = self.agy_client.list_models()
            self.send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "version": "1.3.8",
                    "agy_binary": self.agy_client.binary_path,
                    "agy_installed": self.agy_client.is_installed(),
                    "agy_authenticated": auth_ok,
                    "agy_status_message": auth_msg,
                    "mcp_servers": mcps,
                    "models_count": len(models),
                },
            )
            return

        # 4. MCP List endpoint
        if path == "/api/mcp/list":
            if not self.check_authorization():
                return
            mcps = self.mcp_manager.list_mcp_servers()
            self.send_json(HTTPStatus.OK, {"success": True, "servers": mcps})
            return

        # 5. Models list
        if path == "/api/models":
            if not self.check_authorization():
                return
            models = self.agy_client.list_models()
            self.send_json(HTTPStatus.OK, {"success": True, "models": models})
            return

        # 6. Auth status
        if path == "/api/auth/status":
            auth_ok, auth_msg = self.agy_client.check_auth(timeout=5)
            self.send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "authenticated": auth_ok,
                    "message": auth_msg,
                },
            )
            return

        # Fallback to static web UI files
        if self.serve_static(path):
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": f"Endpoint inconnu : {path}"})

    def do_POST(self) -> None:
        """Handle POST requests."""
        path = self.get_clean_path()

        # Terminal proxy route
        if path.startswith("/terminal"):
            self.proxy_terminal()
            return

        payload = self.read_json_body()
        if payload is None:
            self.send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": "JSON invalide"})
            return

        # 1. Create new conversation
        if path == "/api/conversations":
            if not self.check_authorization():
                return
            title = payload.get("title")
            conv = self.conv_store.create_conversation(title=title)
            self.send_json(HTTPStatus.CREATED, {"success": True, "conversation": conv})
            return

        # 2. Send message in a conversation thread (Streaming SSE or JSON)
        if path.startswith("/api/conversations/") and path.endswith("/send"):
            if not self.check_authorization():
                return
            conv_id = path.replace("/api/conversations/", "").replace("/send", "").strip()
            prompt = payload.get("prompt", "").strip()
            if not prompt:
                self.send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": "Le prompt ne peut pas être vide"})
                return

            # Store user message
            self.conv_store.add_message(conv_id=conv_id, role="user", text=prompt)

            model = payload.get("model")
            effort = payload.get("effort")
            timeout = int(payload.get("timeout", 300))
            stream_mode = payload.get("stream", True)

            if not stream_mode:
                conv = self.conv_store.get_conversation(conv_id)
                target_agy_id = conv.get("agy_conversation_id") if conv else None
                logger.info("Executing agy sync turn for conversation %s (agy_id=%s): '%s...'", conv_id, target_agy_id, prompt[:40])
                result = self.agy_client.process(
                    prompt=prompt,
                    conversation_id=target_agy_id,
                    model=model,
                    effort=effort,
                    dangerously_skip_permissions=True,
                    timeout=timeout,
                )
                actual_agy_id = result.get("conversation_id")
                if actual_agy_id:
                    self.conv_store.set_agy_conversation_id(conv_id, actual_agy_id)

                response_text = result.get("response", "").strip()
                if not response_text:
                    if not result.get("success"):
                        default_err = "Aucune réponse reçue de l'agent."
                        err_msg = result.get("error", default_err)
                        response_text = f"Erreur : {err_msg}"
                    else:
                        response_text = "Action exécutée."

                # Store assistant message
                assistant_msg = self.conv_store.add_message(
                    conv_id=conv_id,
                    role="assistant",
                    text=response_text,
                    tokens=result.get("usage", {}).get("total_tokens"),
                    duration=result.get("duration_seconds"),
                )

                conv = self.conv_store.get_conversation(conv_id)
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "success": result.get("success", False),
                        "message": assistant_msg,
                        "conversation": conv,
                        "status": result.get("status"),
                        "duration_seconds": result.get("duration_seconds"),
                        "usage": result.get("usage", {}),
                    },
                )
                return

            # Start or subscribe to background turn via TurnManager
            turn = self.turn_manager.start_turn(
                conv_id=conv_id,
                prompt=prompt,
                agy_client=self.agy_client,
                conv_store=self.conv_store,
                model=model,
                effort=effort,
                timeout=timeout,
            )

            # Stream live events to this client (turn continues in background if client leaves)
            self.stream_turn_sse(turn)
            return

        # Compact conversation context
        if path.startswith("/api/conversations/") and path.endswith("/compact"):
            if not self.check_authorization():
                return
            conv_id = path.replace("/api/conversations/", "").replace("/compact", "").strip()
            conv = self.conv_store.get_conversation(conv_id)
            target_agy_id = conv.get("agy_conversation_id") if conv else conv_id
            if not target_agy_id:
                self.send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": "Aucune session agy active à compacter"})
                return
            logger.info("Triggering context compaction for conversation %s (agy_id=%s)", conv_id, target_agy_id)
            result = self.agy_client.compact_conversation(conversation_id=target_agy_id, timeout=90)
            self.send_json(
                HTTPStatus.OK,
                {
                    "success": result.get("success", False),
                    "status": result.get("status"),
                    "response": result.get("response", "Conversation compactée avec succès."),
                    "tokens": result.get("usage", {}).get("total_tokens"),
                },
            )
            return

        # 3. Auto-configure MCP with Home Assistant
        if path == "/api/mcp/setup":
            if not self.check_authorization():
                return
            token = payload.get("token") if isinstance(payload, dict) else None
            url = payload.get("url") if isinstance(payload, dict) else None
            success, msg = self.mcp_manager.auto_configure_homeassistant_mcp(custom_token=token, custom_url=url)
            servers = self.mcp_manager.list_mcp_servers()
            self.send_json(HTTPStatus.OK, {"success": success, "message": msg, "servers": servers})
            return

        # 4. Backward-compatible /api/process (for HA Assist conversation entity)
        if path in ("/api/process", "/api/chat"):
            if not self.check_authorization():
                return
            prompt = payload.get("prompt", "")
            if not prompt:
                self.send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": "Prompt requis"})
                return

            conv_id = payload.get("conversation_id")
            model = payload.get("model")
            effort = payload.get("effort")
            timeout = int(payload.get("timeout", 300))

            res = self.agy_client.process(
                prompt=prompt,
                conversation_id=conv_id,
                model=model,
                effort=effort,
                dangerously_skip_permissions=True,
                timeout=timeout,
            )
            status_code = HTTPStatus.OK if res.get("success") else HTTPStatus.INTERNAL_SERVER_ERROR
            self.send_json(status_code, res)
            return

        # 5. Auth check
        if path in ("/api/auth/check", "/api/auth/verify"):
            if not self.check_authorization():
                return
            auth_ok, auth_msg = self.agy_client.check_auth(timeout=5)
            self.send_json(HTTPStatus.OK, {"success": True, "valid": True, "agy_authenticated": auth_ok, "message": auth_msg})
            return

        # 6. Save Gemini API key
        if path == "/api/auth/api-key":
            if not self.check_authorization():
                return
            key = (payload.get("api_key") or "").strip()
            if not key:
                self.send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": "Clé API requise"})
                return
            self.auth_manager.set_gemini_api_key(key)
            auth_ok, auth_msg = self.agy_client.check_auth(timeout=5)
            self.send_json(HTTPStatus.OK, {"success": True, "authenticated": auth_ok, "message": auth_msg})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": f"Endpoint inconnu : {path}"})

    def do_PATCH(self) -> None:
        """Handle PATCH requests (e.g. rename conversation)."""
        path = self.get_clean_path()
        if path.startswith("/api/conversations/"):
            if not self.check_authorization():
                return
            conv_id = path.replace("/api/conversations/", "").strip()
            payload = self.read_json_body() or {}
            new_title = payload.get("title", "").strip()
            if not new_title:
                self.send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": "Titre requis"})
                return
            ok = self.conv_store.rename_conversation(conv_id, new_title)
            if ok:
                self.send_json(HTTPStatus.OK, {"success": True, "conversation": self.conv_store.get_conversation(conv_id)})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": "Conversation non trouvée"})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": f"Endpoint inconnu : {path}"})

    def do_DELETE(self) -> None:
        """Handle DELETE requests (e.g. delete conversation)."""
        path = self.get_clean_path()
        if path.startswith("/api/conversations/"):
            if not self.check_authorization():
                return
            conv_id = path.replace("/api/conversations/", "").strip()
            ok = self.conv_store.delete_conversation(conv_id)
            if ok:
                self.send_json(HTTPStatus.OK, {"success": True, "message": "Conversation supprimée"})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": "Conversation non trouvée"})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": f"Endpoint inconnu : {path}"})

    def log_message(self, format: str, *args: Any) -> None:
        """Custom HTTP request logger."""
        logger.info("%s - %s", self.address_string(), format % args)


class ChassitantBridgeServer(ThreadingHTTPServer):
    """Threaded HTTP Server carrying application state."""

    def __init__(
        self,
        server_address: tuple[str, int],
        auth_manager: AuthManager,
        agy_client: AgyClient,
        conv_store: ConversationStore,
        mcp_manager: McpManager,
        web_dir: Path,
        turn_manager: Optional[TurnManager] = None,
    ) -> None:
        super().__init__(server_address, ChassitantRequestHandler)
        self.auth_manager = auth_manager
        self.agy_client = agy_client
        self.conv_store = conv_store
        self.mcp_manager = mcp_manager
        self.web_dir = web_dir
        self.turn_manager = turn_manager or TurnManager()


def main() -> None:
    """Entry point for the Chassitant Server."""
    auth_mgr = AuthManager()
    agy_cli = AgyClient()
    conv_store = ConversationStore()
    mcp_mgr = McpManager()
    turn_mgr = TurnManager()

    config = auth_mgr.config
    host = config.get("host", "0.0.0.0")
    ingress_port = int(os.getenv("INGRESS_PORT", 8098))
    bridge_port = int(os.getenv("PORT", config.get("port", 8099)))

    # Determine web directory
    web_dir = Path(__file__).resolve().parent.parent / "addon" / "web"
    if not web_dir.is_dir():
        web_dir = Path("/app/web")

    print("=" * 68, flush=True)
    print(" 🌟 CHASSITANT - CHATBOT IA & BRIDGE HOME ASSISTANT 🌟", flush=True)
    print("=" * 68, flush=True)

    # Auto-configure MCP if inside Home Assistant container
    print("🔌 Configuration automatique du serveur MCP Home Assistant...", flush=True)
    mcp_ok, mcp_msg = mcp_mgr.auto_configure_homeassistant_mcp()
    print(f"   -> {mcp_msg}", flush=True)

    auth_ok, auth_msg = agy_cli.check_auth(timeout=5)
    print(f"🔐 Statut Google Antigravity : {auth_msg}", flush=True)

    print(f"🚀 Serveur Chatbot Web UI (Ingress) : http://{host}:{ingress_port}", flush=True)
    print(f"📁 Fichiers statiques Web servis depuis : {web_dir}", flush=True)

    server_ingress = ChassitantBridgeServer((host, ingress_port), auth_mgr, agy_cli, conv_store, mcp_mgr, web_dir, turn_mgr)

    server_bridge = None
    if bridge_port != ingress_port:
        try:
            import threading
            server_bridge = ChassitantBridgeServer((host, bridge_port), auth_mgr, agy_cli, conv_store, mcp_mgr, web_dir, turn_mgr)
            threading.Thread(target=server_bridge.serve_forever, daemon=True).start()
            print(f"🚀 Serveur Assist Bridge (Core API)  : http://{host}:{bridge_port}", flush=True)
        except Exception as err:
            logger.warning("Could not bind bridge port %d: %s", bridge_port, err)

    print("=" * 68 + "\n", flush=True)

    try:
        server_ingress.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur Chassitant...", flush=True)
        server_ingress.server_close()
        if server_bridge:
            server_bridge.server_close()
        sys.exit(0)


if __name__ == "__main__":
    main()

"""Client wrapper for Antigravity CLI (agy)."""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("chassitant.agy")


class AgyClient:
    """Interface to interact with the local Antigravity CLI (agy)."""

    def __init__(self, binary_path: Optional[str] = None) -> None:
        self.binary_path = binary_path or self.find_binary()
        logger.info("Using agy binary at: %s", self.binary_path)

        app_dir = os.environ.get("CHASSITANT_APP_DIR")
        if not app_dir or not os.path.isdir(app_dir):
            if os.path.isdir("/app"):
                app_dir = "/app"
            else:
                app_dir = str(Path(__file__).resolve().parent.parent)
        self.work_dir = app_dir
        logger.info("Using agy work_dir at: %s", self.work_dir)

    @classmethod
    def find_binary(cls) -> Optional[str]:
        """Locate agy executable on the system."""
        # 1. Check in PATH
        found = shutil.which("agy") or shutil.which("agy.exe")
        if found:
            return found

        # 2. Check standard locations on Windows
        if sys.platform.startswith("win"):
            local_appdata = os.getenv("LOCALAPPDATA", "")
            user_profile = os.getenv("USERPROFILE", "")
            candidates = [
                Path(local_appdata) / "agy" / "bin" / "agy.exe",
                Path(user_profile) / ".gemini" / "antigravity-cli" / "bin" / "agy.exe",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)

        # 3. Check standard locations on Linux / macOS
        home = Path.home()
        candidates = [
            home / ".local" / "bin" / "agy",
            Path("/usr/local/bin/agy"),
            home / ".gemini" / "antigravity-cli" / "bin" / "agy",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

        return None

    def is_installed(self) -> bool:
        """Return True if agy binary is found."""
        return self.binary_path is not None and os.path.isfile(self.binary_path)

    def check_auth(self, timeout: int = 15) -> Tuple[bool, str]:
        """
        Check if agy is currently authenticated.
        Returns (is_authenticated, message).
        """
        if not self.is_installed():
            return False, "Le binaire agy n'a pas été trouvé sur le système."

        cmd = [
            self.binary_path,
            "-p",
            "ping",
            "--output-format",
            "json",
            "--print-timeout",
            f"{timeout}s",
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            # Try to parse json output
            if stdout:
                try:
                    data = json.loads(stdout)
                    if data.get("status") == "SUCCESS":
                        return True, "Authentification active et valide."
                except json.JSONDecodeError:
                    pass

            if "auth" in stderr.lower() or "login" in stderr.lower() or "unauthorized" in stderr.lower():
                return False, f"Authentification requise : {stderr or stdout}"

            if res.returncode == 0:
                return True, "Authentification active."

            return False, f"Erreur lors de la vérification ({res.returncode}): {stderr or stdout}"
        except subprocess.TimeoutExpired:
            return False, "Délai d'attente dépassé (authentification requise ou réseau lent)."
        except Exception as err:
            return False, f"Erreur d'exécution: {err}"

    def trigger_interactive_login(self) -> bool:
        """
        Launch agy in interactive mode to let the user authenticate via their browser.
        Blocks until the user completes the flow.
        """
        if not self.is_installed():
            print("❌ Erreur : binaire agy introuvable.")
            return False

        print("\n" + "=" * 60)
        print("🔐 LANCEMENT DE LA CONNEXION GOOGLE ANTIGRAVITY")
        print("Une fenêtre de navigateur va s'ouvrir pour vous connecter.")
        print("=" * 60 + "\n")

        try:
            # Run interactively so the user can see prompts and complete login
            res = subprocess.run([self.binary_path], check=False)
            if res.returncode == 0:
                print("✅ Authentification terminée avec succès !")
                return True
            else:
                print(f"⚠️ agy s'est arrêté avec le code {res.returncode}.")
                return False
        except Exception as err:
            print(f"❌ Échec du lancement de l'authentification : {err}")
            return False

    def list_models(self) -> List[Dict[str, str]]:
        """List available models from agy."""
        if not self.is_installed():
            return []

        try:
            res = subprocess.run(
                [self.binary_path, "models"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            models = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("Fetching"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    models.append({"id": parts[0].strip(), "name": parts[1].strip()})
                elif len(parts) == 1:
                    models.append({"id": parts[0].strip(), "name": parts[0].strip()})
            return models
        except Exception as err:
            logger.warning("Failed to list models: %s", err)
            return []

    def list_mcp_servers(self) -> List[Dict[str, str]]:
        """List configured MCP servers from agy."""
        if not self.is_installed():
            return []

        try:
            res = subprocess.run(
                [self.binary_path, "mcp", "list"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            servers = []
            lines = res.stdout.splitlines()
            for line in lines[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 3:
                    servers.append({
                        "name": parts[0],
                        "type": parts[1],
                        "status": parts[2],
                        "target": " ".join(parts[3:]) if len(parts) > 3 else "",
                    })
            return servers
        except Exception as err:
            logger.warning("Failed to list MCP servers: %s", err)
            return []

    def process(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        dangerously_skip_permissions: bool = True,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """
        Execute a prompt using agy -p and return structured JSON result.
        """
        if not self.is_installed():
            return {
                "success": False,
                "error": "Agy binary not found on host",
                "status": "ERROR",
            }

        cmd = [self.binary_path, "-p", prompt, "--output-format", "json"]

        if conversation_id and str(conversation_id).strip():
            cmd.extend(["--conversation", str(conversation_id).strip()])

        if model and model != "default":
            cmd.extend(["--model", model])

        eff = (effort or "").strip().lower()
        if not eff or eff == "default":
            eff = "low"
        elif eff in ("high", "max", "xhigh"):
            logger.info("Capping effort '%s' to 'medium' to avoid 300s thinking stall on multi-tool HA operations", eff)
            eff = "medium"
        cmd.extend(["--effort", eff])

        if dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        # Set 0s so agy waits until completion without premature turn cutoff
        cmd.extend(["--print-timeout", "0s"])

        effective_timeout = max(timeout, 300) if timeout > 0 else 300
        logger.info("Executing agy prompt (effort=%s, timeout=%ds)...", eff, effective_timeout)

        try:
            # Subprocess execution timeout with safety margin
            exec_timeout = effective_timeout + 60
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=exec_timeout,
                check=False,
                encoding="utf-8",
                errors="replace",
                cwd=self.work_dir,
            )

            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            if stdout:
                try:
                    data = json.loads(stdout)
                    data["success"] = (data.get("status") == "SUCCESS")
                    return data
                except json.JSONDecodeError:
                    # Output might have non-json prefix/suffix
                    # Try to find json block
                    start = stdout.find("{")
                    end = stdout.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        try:
                            data = json.loads(stdout[start : end + 1])
                            data["success"] = (data.get("status") == "SUCCESS")
                            return data
                        except json.JSONDecodeError:
                            pass

                    # Fallback to plain text if JSON couldn't be parsed
                    return {
                        "success": res.returncode == 0,
                        "status": "SUCCESS" if res.returncode == 0 else "ERROR",
                        "response": stdout,
                        "conversation_id": conversation_id,
                    }

            if res.returncode != 0:
                logger.error("agy exited with %d: %s", res.returncode, stderr)
                return {
                    "success": False,
                    "status": "ERROR",
                    "error": stderr or f"Process exited with code {res.returncode}",
                    "conversation_id": conversation_id,
                }

            return {
                "success": False,
                "status": "EMPTY",
                "error": "Empty output from agy",
                "conversation_id": conversation_id,
            }

        except subprocess.TimeoutExpired:
            logger.error("agy execution timed out after %ds", timeout)
            return {
                "success": False,
                "status": "TIMEOUT",
                "error": f"L'agent n'a pas répondu dans le délai imparti ({timeout}s).",
                "conversation_id": conversation_id,
            }
        except Exception as err:
            logger.exception("Error executing agy: %s", err)
            return {
                "success": False,
                "status": "EXCEPTION",
                "error": str(err),
                "conversation_id": conversation_id,
            }

    def process_stream(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        dangerously_skip_permissions: bool = True,
        timeout: int = 300,
        on_proc_started: Optional[Callable[[subprocess.Popen], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Execute agy with --output-format stream-json and yield parsed events in real time.
        Yields events:
          - {"type": "status", "message": ...}
          - {"type": "init", "conversation_id": ..., "tools_count": ...}
          - {"type": "tool_start", "tool": ..., "parameters": ..., "step_index": ...}
          - {"type": "tool_end", "tool": ..., "duration": ..., "output": ...}
          - {"type": "text_delta", "delta": ...}
          - {"type": "done", "response": ..., "duration_seconds": ..., "usage": ...}
          - {"type": "cancelled", "message": ...}
          - {"type": "error", "error": ...}
        """
        if not self.is_installed():
            yield {
                "type": "error",
                "error": "Binaire agy introuvable sur le système hôte.",
            }
            return

        cmd = [self.binary_path, "-p", prompt, "--output-format", "stream-json"]
        if conversation_id and str(conversation_id).strip():
            cmd.extend(["--conversation", str(conversation_id).strip()])
        if model and model != "default":
            cmd.extend(["--model", model])

        eff = (effort or "").strip().lower()
        if not eff or eff == "default":
            eff = "low"
        elif eff in ("high", "max", "xhigh"):
            logger.info("Capping effort '%s' to 'medium' to avoid 300s thinking stall on multi-tool HA operations", eff)
            eff = "medium"
        cmd.extend(["--effort", eff])

        if dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        cmd.extend(["--print-timeout", "0s"])

        logger.info("Starting agy stream turn (effort=%s): '%s...'", eff, prompt[:50])
        yield {
            "type": "status",
            "message": "Connexion à Gemini en cours...",
        }

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self.work_dir,
            )
            if on_proc_started:
                try:
                    on_proc_started(proc)
                except Exception as ex:
                    logger.debug("on_proc_started hook error: %s", ex)

            full_response: List[str] = []
            final_result: Optional[Dict[str, Any]] = None

            for line in proc.stdout:
                if cancel_event and cancel_event.is_set():
                    logger.info("Stream interrupted via cancel_event")
                    break

                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                event = data.get("event")
                if event == "init":
                    init_data = data.get("init", {})
                    conv_id = data.get("conversation_id")
                    tools_available = init_data.get("tools", [])
                    yield {
                        "type": "init",
                        "conversation_id": conv_id,
                        "tools_count": len(tools_available),
                        "message": "Agent initialisé, analyse de votre demande...",
                    }

                elif event == "step_update":
                    su = data.get("step_update", {})
                    stype = su.get("step_type")
                    state = su.get("state")

                    if stype == "tool":
                        tool_name = su.get("tool_name") or "outil"
                        idx = su.get("step_index")
                        if state == "ACTIVE":
                            info = su.get("tool_info", {})
                            params = info.get("parameters", {})
                            yield {
                                "type": "tool_start",
                                "tool": tool_name,
                                "parameters": params,
                                "step_index": idx,
                            }
                        elif state == "DONE":
                            dur = su.get("duration_seconds", 0)
                            info = su.get("tool_info", {})
                            output = info.get("output", "")
                            yield {
                                "type": "tool_end",
                                "tool": tool_name,
                                "duration": dur,
                                "output": output,
                                "step_index": idx,
                            }

                    elif stype == "agent_response":
                        delta = su.get("text_delta")
                        if delta:
                            full_response.append(delta)
                            yield {
                                "type": "text_delta",
                                "delta": delta,
                            }

                elif event == "result":
                    final_result = data.get("result", {})

            if cancel_event and cancel_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                yield {
                    "type": "cancelled",
                    "message": "Génération interrompue par l'utilisateur",
                }
                return

            proc.wait()

            if final_result:
                resp_text = final_result.get("response") or "".join(full_response)
                yield {
                    "type": "done",
                    "response": resp_text,
                    "status": final_result.get("status", "SUCCESS"),
                    "duration_seconds": final_result.get("duration_seconds", 0),
                    "usage": final_result.get("usage", {}),
                    "conversation_id": final_result.get("conversation_id") or conversation_id,
                }
            else:
                stderr_text = proc.stderr.read() if proc.stderr else ""
                resp_text = "".join(full_response)
                if proc.returncode == 0 and resp_text:
                    yield {
                        "type": "done",
                        "response": resp_text,
                        "status": "SUCCESS",
                        "conversation_id": conversation_id,
                    }
                else:
                    err_msg = stderr_text.strip() or f"Le processus agy s'est arrêté (code {proc.returncode})"
                    yield {"type": "error", "error": err_msg}

        except Exception as err:
            if cancel_event and cancel_event.is_set():
                yield {
                    "type": "cancelled",
                    "message": "Génération interrompue par l'utilisateur",
                }
                return
            logger.exception("Stream execution error: %s", err)
            yield {"type": "error", "error": str(err)}

    def compact_conversation(self, conversation_id: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Run context compaction on a conversation to trim historical tokens and keep it snappy.
        """
        return self.process(
            prompt="/compact",
            conversation_id=conversation_id,
            effort="low",
            timeout=timeout,
        )

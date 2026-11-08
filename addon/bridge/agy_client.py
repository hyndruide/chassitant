"""Client wrapper for Antigravity CLI (agy)."""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("chassitant.agy")


class AgyClient:
    """Interface to interact with the local Antigravity CLI (agy)."""

    def __init__(self, binary_path: Optional[str] = None) -> None:
        self.binary_path = binary_path or self.find_binary()
        logger.info("Using agy binary at: %s", self.binary_path)

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

        if conversation_id:
            cmd.extend(["--conversation", conversation_id])

        if model and model != "default":
            cmd.extend(["--model", model])

        if effort:
            cmd.extend(["--effort", effort])

        if dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        if timeout > 0:
            cmd.extend(["--print-timeout", f"{timeout}s"])

        logger.info("Executing agy prompt (timeout=%ds)...", timeout)

        try:
            # We add a buffer of 15 seconds over print-timeout for process startup/cleanup
            exec_timeout = timeout + 15 if timeout > 0 else None
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=exec_timeout,
                check=False,
                encoding="utf-8",
                errors="replace",
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

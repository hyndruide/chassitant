"""OpenAI Codex CLI Provider implementation for Françoise."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from bridge.providers.base import BaseProvider

logger = logging.getLogger("chassitant.providers.codex")


class CodexProvider(BaseProvider):
    """Provider integrating OpenAI's official Codex CLI connected to ChatGPT."""

    def __init__(self, binary_path: Optional[str] = None) -> None:
        self.binary_path = binary_path or self.find_binary()
        app_dir = os.environ.get("CHASSITANT_APP_DIR")
        if not app_dir or not os.path.isdir(app_dir):
            if os.path.isdir("/app"):
                app_dir = "/app"
            else:
                app_dir = str(Path(__file__).resolve().parent.parent.parent)
        self.work_dir = app_dir
        logger.info("Initialized CodexProvider with binary: %s (work_dir=%s)", self.binary_path, self.work_dir)

    @classmethod
    def find_binary(cls) -> Optional[str]:
        """Locate codex executable."""
        found = shutil.which("codex") or shutil.which("codex.exe")
        if found:
            return found

        home = Path.home()
        candidates = [
            home / ".local" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            Path("/usr/bin/codex"),
            home / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return None

    @property
    def provider_id(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "OpenAI Codex CLI (Compte ChatGPT)"

    @property
    def description(self) -> str:
        return "Agent officiel OpenAI connecté à votre compte ChatGPT (Plus, Pro, Team). Quota forfaitaire, 0 € par token."

    def is_configured(self) -> bool:
        return self.binary_path is not None and os.path.isfile(self.binary_path)

    def check_auth(self, timeout: int = 15) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "Le binaire 'codex' n'est pas encore installé sur le système."

        # Check for auth file or test via CLI
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        auth_file = codex_home / "auth.json"
        if auth_file.is_file():
            return True, "Session ChatGPT active !"

        try:
            res = subprocess.run(
                [self.binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if res.returncode == 0:
                return True, f"Codex CLI opérationnel ({res.stdout.strip()}). Connectez votre compte via le Terminal."
            return False, res.stderr.strip() or "Erreur de vérification Codex."
        except Exception as ex:
            return False, str(ex)

    def list_models(self) -> List[Dict[str, str]]:
        return [
            {"id": "default", "name": "ChatGPT (Par défaut / Auto)"},
            {"id": "gpt-4o", "name": "GPT-4o (Omni)"},
            {"id": "o3-mini", "name": "o3-mini (Raisonnement rapide)"},
            {"id": "o1", "name": "o1 (Raisonnement avancé)"},
        ]

    def process_stream(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        timeout: int = 300,
        pre_prompt: Optional[str] = None,
        on_proc_started: Optional[Callable[[Any], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> Iterator[Dict[str, Any]]:
        if not self.is_configured():
            yield {
                "type": "error",
                "error": "Binaire 'codex' introuvable. Veuillez l'installer ou utiliser le terminal Ingress.",
            }
            return

        yield {"type": "status", "message": "Initialisation d'OpenAI Codex CLI..."}
        yield {"type": "init", "conversation_id": conversation_id or "default"}

        effective_prompt = prompt
        if pre_prompt and pre_prompt.strip():
            effective_prompt = f"[Consignes système : {pre_prompt.strip()}]\n\n{prompt}"

        cmd = [self.binary_path, "exec", effective_prompt, "--full-auto"]
        if model and model != "default":
            cmd.extend(["--model", model])

        logger.info("Launching Codex CLI command: %s", " ".join(cmd[:3]))
        start_time = time.time()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=self.work_dir,
                env=os.environ.copy(),
            )

            if on_proc_started:
                on_proc_started(proc)

            accumulated_text = ""
            for line in iter(proc.stdout.readline, ""):
                if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                    proc.terminate()
                    yield {"type": "cancelled", "message": "Génération interrompue par l'utilisateur"}
                    return

                accumulated_text += line
                yield {"type": "text_delta", "delta": line}

            proc.stdout.close()
            ret_code = proc.wait(timeout=max(timeout - int(time.time() - start_time), 5))

            if ret_code != 0:
                logger.warning("Codex CLI exited with non-zero code %d", ret_code)

            duration = time.time() - start_time
            yield {
                "type": "done",
                "response": accumulated_text.strip(),
                "duration_seconds": duration,
            }

        except Exception as err:
            logger.error("Error running Codex CLI: %s", err)
            yield {"type": "error", "error": f"Erreur lors de l'exécution de Codex CLI : {err}"}

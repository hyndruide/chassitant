"""OpenAI Codex CLI Provider implementation for Françoise."""

from __future__ import annotations

import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
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
        self._cached_flags: Optional[List[str]] = None
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

    def _detect_exec_flags(self) -> List[str]:
        """Detect supported non-interactive/sandbox flags from codex exec --help."""
        flags: List[str] = []
        if not self.binary_path:
            return flags

        try:
            res = subprocess.run(
                [self.binary_path, "exec", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            help_text = (res.stdout or "") + " " + (res.stderr or "")
            if "--dangerously-bypass-approvals-and-sandbox" in help_text:
                flags.append("--dangerously-bypass-approvals-and-sandbox")
            elif "--yolo" in help_text:
                flags.append("--yolo")
        except Exception as ex:
            logger.debug("Failed to query codex exec --help: %s", ex)
            flags.append("--dangerously-bypass-approvals-and-sandbox")
        return flags

    def get_exec_flags(self) -> List[str]:
        if self._cached_flags is None:
            self._cached_flags = self._detect_exec_flags()
        return list(self._cached_flags)

    def build_command(self, prompt: str, model: Optional[str] = None) -> List[str]:
        """Build the codex exec command list following the [OPTIONS] [PROMPT] syntax."""
        if not self.binary_path:
            raise RuntimeError("Binary path is not set")
        cmd = [self.binary_path, "exec"]
        cmd.extend(self.get_exec_flags())

        if model and model != "default":
            cmd.extend(["--model", model])

        # The prompt MUST always be the last positional argument
        cmd.append(prompt)
        return cmd

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

        cmd = self.build_command(effective_prompt, model=model)
        logger.info("Launching Codex CLI command: %s (args=%d)", cmd[0], len(cmd))
        start_time = time.time()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self.work_dir,
                env=os.environ.copy(),
            )

            if on_proc_started:
                on_proc_started(proc)

            event_queue: queue.Queue[Tuple[str, Optional[str]]] = queue.Queue()

            def drain_stdout() -> None:
                try:
                    if proc.stdout:
                        for line in iter(proc.stdout.readline, ""):
                            event_queue.put(("stdout", line))
                except Exception:
                    pass
                finally:
                    event_queue.put(("stdout_done", None))

            def drain_stderr() -> None:
                try:
                    if proc.stderr:
                        for line in iter(proc.stderr.readline, ""):
                            event_queue.put(("stderr", line))
                except Exception:
                    pass
                finally:
                    event_queue.put(("stderr_done", None))

            t_out = threading.Thread(target=drain_stdout, daemon=True)
            t_err = threading.Thread(target=drain_stderr, daemon=True)
            t_out.start()
            t_err.start()

            accumulated_text = ""
            stderr_lines: List[str] = []
            stdout_done = False

            while True:
                if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                    proc.terminate()
                    yield {"type": "cancelled", "message": "Génération interrompue par l'utilisateur"}
                    return

                try:
                    stream_type, data = event_queue.get(timeout=0.1)
                except queue.Empty:
                    if stdout_done and proc.poll() is not None:
                        break
                    continue

                if stream_type == "stdout" and data:
                    accumulated_text += data
                    yield {"type": "text_delta", "delta": data}
                elif stream_type == "stderr" and data:
                    line_s = data.strip()
                    if line_s:
                        stderr_lines.append(line_s)
                        yield {"type": "status", "message": f"Codex : {line_s[:100]}"}
                elif stream_type == "stdout_done":
                    stdout_done = True
                    if proc.poll() is not None and event_queue.empty():
                        break

            t_out.join(timeout=2)
            t_err.join(timeout=2)
            ret_code = proc.wait(timeout=max(timeout - int(time.time() - start_time), 5))

            if ret_code != 0:
                err_details = "\n".join(stderr_lines).strip() or accumulated_text.strip() or f"Code sortie {ret_code}"
                logger.warning("Codex CLI exited with code %d: %s", ret_code, err_details)
                yield {
                    "type": "error",
                    "error": f"Erreur Codex CLI ({ret_code}) :\n{err_details}",
                }
                return

            final_text = accumulated_text.strip()
            if not final_text and stderr_lines:
                final_text = "\n".join(stderr_lines).strip()

            duration = time.time() - start_time
            yield {
                "type": "done",
                "response": final_text,
                "duration_seconds": duration,
            }

        except Exception as err:
            logger.error("Error running Codex CLI: %s", err)
            yield {"type": "error", "error": f"Erreur lors de l'exécution de Codex CLI : {err}"}

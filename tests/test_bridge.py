"""Unit and integration tests for Chassitant Bridge."""

import json
import os
import threading
import time
import unittest
from http import HTTPStatus
from pathlib import Path
from urllib import request
from urllib.error import HTTPError

from bridge.agy_client import AgyClient
from bridge.auth_manager import AuthManager
from bridge.server import ChassitantBridgeServer


class TestAuthManager(unittest.TestCase):
    """Test suite for token and config management."""

    def setUp(self) -> None:
        self.test_dir = Path(__file__).resolve().parent / "tmp_test"
        self.test_dir.mkdir(exist_ok=True)
        self.config_file = self.test_dir / "chassitant_config.json"
        if self.config_file.exists():
            self.config_file.unlink()

    def tearDown(self) -> None:
        if self.config_file.exists():
            self.config_file.unlink()
        if self.test_dir.exists():
            self.test_dir.rmdir()

    def test_token_generation_and_validation(self) -> None:
        mgr = AuthManager(config_dir=self.test_dir)
        token = mgr.get_api_key()

        self.assertTrue(len(token) >= 20)
        self.assertTrue(mgr.validate_token(token))
        self.assertFalse(mgr.validate_token("wrong-token"))
        self.assertFalse(mgr.validate_token(None))
        self.assertFalse(mgr.validate_token(""))

    def test_env_var_override(self) -> None:
        os.environ["CHASSITANT_API_KEY"] = "custom_secret_key_123"
        try:
            mgr = AuthManager(config_dir=self.test_dir)
            self.assertEqual(mgr.get_api_key(), "custom_secret_key_123")
            self.assertTrue(mgr.validate_token("custom_secret_key_123"))
        finally:
            del os.environ["CHASSITANT_API_KEY"]


class TestBridgeServer(unittest.TestCase):
    """Test suite for Bridge HTTP server endpoints."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = Path(__file__).resolve().parent / "tmp_test_server"
        cls.test_dir.mkdir(exist_ok=True)
        cls.auth_mgr = AuthManager(config_dir=cls.test_dir)
        cls.token = cls.auth_mgr.get_api_key()
        cls.agy_cli = AgyClient()
        cls.port = 18099
        cls.server = ChassitantBridgeServer(("127.0.0.1", cls.port), cls.auth_mgr, cls.agy_cli)

        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        config_file = cls.test_dir / "chassitant_config.json"
        if config_file.exists():
            config_file.unlink()
        if cls.test_dir.exists():
            cls.test_dir.rmdir()

    def test_status_local_exemption(self) -> None:
        """Verify local access (127.0.0.1) succeeds without token."""
        url = f"http://127.0.0.1:{self.port}/api/status"
        req = request.Request(url)
        with request.urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

    def test_status_authorized(self) -> None:
        """Verify /api/status returns valid JSON with correct token."""
        url = f"http://127.0.0.1:{self.port}/api/status"
        req = request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        with request.urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertTrue(data.get("agy_installed"))
            self.assertIn("agy_authenticated", data)

    def test_auth_check(self) -> None:
        """Verify /api/auth/check endpoint."""
        url = f"http://127.0.0.1:{self.port}/api/auth/check"
        req = request.Request(
            url,
            data=b"{}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("valid"))

    def test_providers_endpoint(self) -> None:
        """Verify /api/providers endpoint lists available providers."""
        url = f"http://127.0.0.1:{self.port}/api/providers"
        req = request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("active_provider", data)
            providers = data.get("providers", [])
            provider_ids = [p["id"] for p in providers]
            self.assertIn("agy", provider_ids)
            self.assertIn("codex", provider_ids)
            self.assertIn("groq", provider_ids)
            self.assertIn("openrouter", provider_ids)
            self.assertIn("ollama", provider_ids)

    def test_providers_select_and_config(self) -> None:
        """Verify selecting and configuring a provider."""
        # 1. Select Groq
        url_select = f"http://127.0.0.1:{self.port}/api/providers/select"
        req_select = request.Request(
            url_select,
            data=json.dumps({"provider": "groq"}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req_select) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("active_provider"), "groq")

        # 2. Configure Groq Key
        url_cfg = f"http://127.0.0.1:{self.port}/api/providers/config"
        req_cfg = request.Request(
            url_cfg,
            data=json.dumps({"provider": "groq", "config": {"api_key": "gsk_test_key_123"}}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req_cfg) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

        # 3. Switch back to agy
        req_back = request.Request(
            url_select,
            data=json.dumps({"provider": "agy"}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req_back) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("active_provider"), "agy")

    def test_process_empty_prompt(self) -> None:
        """Verify 400 Bad Request when prompt is empty."""
        url = f"http://127.0.0.1:{self.port}/api/process"
        req = request.Request(
            url,
            data=json.dumps({"prompt": ""}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            request.urlopen(req)
        self.assertEqual(ctx.exception.code, HTTPStatus.BAD_REQUEST)

    def test_codex_provider_command_structure(self) -> None:
        """Verify CodexProvider builds valid command lines matching 'codex exec [OPTIONS] [PROMPT]'."""
        from bridge.providers.codex_provider import CodexProvider
        provider = CodexProvider(binary_path="/usr/local/bin/codex")
        provider._cached_flags = ["--dangerously-bypass-approvals-and-sandbox"]

        cmd = provider.build_command("Hello assistant", model="gpt-4o")
        self.assertEqual(cmd[0], "/usr/local/bin/codex")
        self.assertEqual(cmd[1], "exec")
        self.assertNotIn("--full-auto", cmd)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        self.assertIn("--model", cmd)
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "gpt-4o")
        # Prompt must be the very last element
        self.assertEqual(cmd[-1], "Hello assistant")

    def test_codex_provider_env_and_flags(self) -> None:
        """Verify CodexProvider sanitizes environment variables and recognizes flags."""
        from bridge.providers.codex_provider import CodexProvider
        provider = CodexProvider(binary_path="/usr/local/bin/codex", api_key="")
        provider._cached_flags = ["--ephemeral", "--dangerously-bypass-approvals-and-sandbox"]
        cmd = provider.build_command("Test prompt", model="default")
        self.assertEqual(cmd[-1], "Test prompt")
        self.assertIn("--ephemeral", cmd)
        self.assertNotIn("--model", cmd)

    def test_token_usage_normalization(self) -> None:
        """Verify normalization of token metrics and context remaining calculation."""
        from bridge.turn_manager import normalize_token_usage, get_model_context_limit

        # 1. Gemini on agy (1M context)
        raw_agy = {
            "input_tokens": 10500,
            "output_tokens": 500,
            "thinking_tokens": 200,
            "total_tokens": 11000,
        }
        res = normalize_token_usage(raw_agy, provider_id="agy", model="gemini-2.5-flash")
        self.assertEqual(res["context_limit"], 1_048_576)
        self.assertEqual(res["total_tokens"], 11000)
        self.assertEqual(res["input_tokens"], 10500)
        self.assertEqual(res["thinking_tokens"], 200)
        self.assertEqual(res["remaining_tokens"], 1_048_576 - 11000)
        self.assertAlmostEqual(res["remaining_percent"], round((1_048_576 - 11000) / 1_048_576 * 100, 1))
        self.assertEqual(res["source"], "exact")

        # 2. Claude (200k context)
        self.assertEqual(get_model_context_limit("agy", "claude-3-5-sonnet"), 200_000)

        # 3. GPT-4o (128k context)
        self.assertEqual(get_model_context_limit("codex", "gpt-4o"), 128_000)

        # 4. Fallback estimation
        est = normalize_token_usage({}, provider_id="codex", model="gpt-4o", prompt_text="A" * 380, response_text="B" * 380)
        self.assertEqual(est["source"], "estimated")
        self.assertTrue(est["input_tokens"] > 0)
        self.assertTrue(est["output_tokens"] > 0)
        self.assertEqual(est["context_limit"], 128_000)

    def test_conversation_store_usage_persistence(self) -> None:
        """Verify usage data is persisted and returned in list_conversations and get_conversation."""
        from bridge.conversation_store import ConversationStore
        import tempfile
        import shutil

        temp_dir = Path(tempfile.mkdtemp())
        try:
            store = ConversationStore(data_dir=temp_dir)
            conv = store.create_conversation(title="Test Usage Thread")
            usage_data = {
                "input_tokens": 1200,
                "output_tokens": 80,
                "total_tokens": 1280,
                "remaining_percent": 99.0,
            }
            msg = store.add_message(
                conv_id=conv["id"],
                role="assistant",
                text="Message avec usage",
                tokens=1280,
                duration=1.5,
                usage=usage_data,
            )
            self.assertEqual(msg["usage"], usage_data)

            # Reload from disk
            store2 = ConversationStore(data_dir=temp_dir)
            fetched = store2.get_conversation(conv["id"])
            self.assertIsNotNone(fetched)
            self.assertEqual(len(fetched["messages"]), 1)
            self.assertEqual(fetched["messages"][0]["usage"], usage_data)

            # Check list_conversations includes last_usage
            conv_list = store2.list_conversations()
            self.assertEqual(len(conv_list), 1)
            self.assertEqual(conv_list[0]["last_usage"], usage_data)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

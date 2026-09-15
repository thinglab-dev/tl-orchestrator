"""Testes do scripts/tl_tools.py: funções puras, estado e hook de sessão sem rede."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tl_tools.py"
ENV_KEYS = (
    "TL_TOOLS_USER_HOME",
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "APPDATA",
    "XDG_CONFIG_HOME",
    "TL_TOOLS_HOME",
    "TL_TOOLS_OFFLINE",
    "TL_TOOLS_HEADROOM_EXE",
    "PONYTAIL_DEFAULT_MODE",
    "CAVEMAN_DEFAULT_MODE",
    "ANTHROPIC_BASE_URL",
    "UV_TOOL_DIR",
)


def load_module():
    spec = importlib.util.spec_from_file_location("tl_tools_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TlToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = load_module()
        self.tmp = tempfile.TemporaryDirectory(prefix="tl-tools-test-")
        self.root = Path(self.tmp.name)
        self.saved = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(
            {
                "TL_TOOLS_USER_HOME": str(self.root / "home"),
                "CLAUDE_CONFIG_DIR": str(self.root / "claude"),
                "CODEX_HOME": str(self.root / "codex"),
                "APPDATA": str(self.root / "appdata"),
                "XDG_CONFIG_HOME": str(self.root / "appdata"),
                "TL_TOOLS_HOME": str(self.root / "claude" / "tl-tools"),
                "TL_TOOLS_OFFLINE": "1",
                "UV_TOOL_DIR": str(self.root / "uv-tools"),
            }
        )
        self.paths = self.tools.Paths.from_env()
        self.config = self.tools.load_config(self.paths)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    # ----------------------------------------------------------------- settings

    def test_add_hook_is_idempotent_and_removable(self) -> None:
        settings: dict = {}
        command = 'python "/x/tl_tools.py" session-hook'
        self.assertTrue(self.tools.add_hook(settings, "SessionStart", "startup", command, 45))
        self.assertFalse(self.tools.add_hook(settings, "SessionStart", "startup", command, 45))
        self.assertEqual(len(settings["hooks"]["SessionStart"]), 1)
        self.assertTrue(self.tools.hook_present(settings, "SessionStart", "tl_tools.py"))
        self.assertTrue(self.tools.remove_hook(settings, "SessionStart", "tl_tools.py"))
        self.assertEqual(settings, {})

    def test_remove_hook_keeps_foreign_hooks(self) -> None:
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]},
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "python guard.py"}]},
                ]
            }
        }
        self.assertTrue(self.tools.remove_hook(settings, "PreToolUse", "rtk hook claude"))
        remaining = settings["hooks"]["PreToolUse"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["hooks"][0]["command"], "python guard.py")

    def test_env_helpers_preserve_other_keys(self) -> None:
        settings = {"env": {"KEEP": "1"}, "model": "opus"}
        self.assertTrue(self.tools.set_env(settings, "ANTHROPIC_BASE_URL", "http://127.0.0.1:8790"))
        self.assertFalse(self.tools.set_env(settings, "ANTHROPIC_BASE_URL", "http://127.0.0.1:8790"))
        self.assertEqual(settings["env"]["KEEP"], "1")
        self.assertTrue(self.tools.unset_env(settings, "ANTHROPIC_BASE_URL"))
        self.assertFalse(self.tools.unset_env(settings, "ANTHROPIC_BASE_URL"))
        self.assertEqual(settings, {"env": {"KEEP": "1"}, "model": "opus"})

    def test_write_mode_preserves_other_keys_and_validates(self) -> None:
        path = self.paths.tool_config("caveman")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"other": True}), encoding="utf-8")
        self.assertTrue(self.tools.write_mode(self.paths, "caveman", "lite"))
        self.assertFalse(self.tools.write_mode(self.paths, "caveman", "lite"))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"other": True, "defaultMode": "lite"})
        self.assertEqual(self.tools.read_mode(self.paths, "caveman"), "lite")
        with self.assertRaises(ValueError):
            self.tools.write_mode(self.paths, "caveman", "loud")

    # ------------------------------------------------------------------- estado

    def test_status_on_empty_machine_reports_everything_inactive(self) -> None:
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self.root / "empty-bin")
        try:
            status = self.tools.collect_status(self.paths, self.config, probe_proxy=False)
        finally:
            os.environ["PATH"] = old_path
        self.assertFalse(status["hook"])
        for tool in self.tools.TOOLS:
            self.assertFalse(self.tools.tool_active(status["tools"][tool], tool), tool)
        line = self.tools.brief_line(status)
        self.assertTrue(line.startswith("tl-tools: "))
        self.assertEqual(line.count("INATIVO"), 4)

    def test_status_on_configured_machine_reports_active(self) -> None:
        paths = self.paths
        url = self.tools.proxy_url(self.config)
        settings = {
            "env": {"ANTHROPIC_BASE_URL": url},
            "enabledPlugins": {"ponytail@ponytail": True, "caveman@caveman": True},
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": 'python "x/tl_tools.py" session-hook'}]}],
            },
        }
        paths.claude.mkdir(parents=True)
        paths.settings.write_text(json.dumps(settings), encoding="utf-8")
        for tool in ("ponytail", "caveman"):
            (paths.claude / "plugins" / "cache" / tool / tool / "1.0.0").mkdir(parents=True)
        self.tools.write_mode(paths, "ponytail", "full")
        self.tools.write_mode(paths, "caveman", "lite")
        paths.local_bin.mkdir(parents=True)
        (paths.local_bin / ("rtk.exe" if os.name == "nt" else "rtk")).write_bytes(b"")
        fake_headroom = self.root / "headroom-bin"
        fake_headroom.write_bytes(b"")
        os.environ["TL_TOOLS_HEADROOM_EXE"] = str(fake_headroom)
        paths.codex.mkdir(parents=True)
        (paths.codex / "AGENTS.md").write_text("@RTK.md\n", encoding="utf-8")
        (paths.codex / "config.toml").write_text('[plugins."ponytail@ponytail"]\nenabled = true\n', encoding="utf-8")
        skill = paths.agents_skills / "caveman" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# caveman\n", encoding="utf-8")
        self.assertTrue(self.tools.write_codex_block(paths, self.config))
        self.assertFalse(self.tools.write_codex_block(paths, self.config), "segunda escrita é idempotente")
        agents = (paths.codex / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(self.tools.CODEX_BLOCK_START), 1)
        self.assertIn("`ponytail` no nível `full`", agents)
        self.assertIn("`caveman` no nível `lite`", agents)
        env = json.loads(paths.settings.read_text(encoding="utf-8"))["env"]
        self.assertEqual(env["CAVEMAN_DEFAULT_MODE"], "lite")
        self.assertEqual(env["PONYTAIL_DEFAULT_MODE"], "full")
        self.assertEqual(self.tools.caveman_flag_mode(paths), "lite")

        status = self.tools.collect_status(paths, self.config, probe_proxy=False)
        self.assertTrue(status["hook"])
        tools = status["tools"]
        self.assertTrue(self.tools.tool_active(tools["rtk"], "rtk"))
        self.assertTrue(tools["rtk"]["codex"])
        self.assertTrue(tools["headroom"]["installed"])
        self.assertTrue(tools["headroom"]["claude"])
        self.assertFalse(tools["headroom"]["proxy"], "sem sonda o proxy conta como fora do ar")
        self.assertTrue(self.tools.tool_active(tools["ponytail"], "ponytail"))
        self.assertEqual(tools["ponytail"]["mode"], "full")
        self.assertTrue(tools["ponytail"]["codex"])
        self.assertTrue(self.tools.tool_active(tools["caveman"], "caveman"))
        self.assertEqual(tools["caveman"]["mode"], "lite")
        self.assertTrue(tools["caveman"]["codex"])
        line = self.tools.brief_line(status)
        self.assertIn("rtk ok", line)
        self.assertIn("ponytail full", line)
        self.assertIn("caveman lite", line)
        self.assertIn("headroom INATIVO", line)

    def test_mode_off_makes_plugin_inactive(self) -> None:
        entry = {"enabled": True, "claude": True, "mode": "off"}
        self.assertFalse(self.tools.tool_active(entry, "caveman"))
        entry["mode"] = "lite"
        self.assertTrue(self.tools.tool_active(entry, "caveman"))

    def test_codex_plugin_detection_respects_enabled_false(self) -> None:
        self.paths.codex.mkdir(parents=True)
        config = self.paths.codex / "config.toml"
        config.write_text('[plugins."ponytail@ponytail"]\nenabled = false\n', encoding="utf-8")
        self.assertFalse(self.tools.codex_plugin_enabled(self.paths, "ponytail@ponytail"))
        config.write_text('[plugins."ponytail@ponytail"]\n', encoding="utf-8")
        self.assertTrue(self.tools.codex_plugin_enabled(self.paths, "ponytail@ponytail"))

    def test_rtk_asset_table_covers_common_platforms(self) -> None:
        for key in (("windows", "amd64"), ("linux", "x86_64"), ("darwin", "arm64")):
            self.assertIn(key, self.tools.RTK_ASSETS)
        self.assertIn(self.tools.rtk_asset_name(), set(self.tools.RTK_ASSETS.values()) | {None})

    def test_config_merges_defaults_with_stored_overrides(self) -> None:
        self.paths.home.mkdir(parents=True)
        self.paths.config.write_text(json.dumps({"tools": {"caveman": False}, "headroom": {"port": 9000}}), encoding="utf-8")
        config = self.tools.load_config(self.paths)
        self.assertFalse(config["tools"]["caveman"])
        self.assertTrue(config["tools"]["rtk"])
        self.assertEqual(config["headroom"]["port"], 9000)
        self.assertEqual(config["headroom"]["mode"], "cache")

    # --------------------------------------------------------------- instalação

    def test_install_dry_run_plans_without_writing(self) -> None:
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self.root / "empty-bin")
        try:
            installer = self.tools.Installer(self.paths, self.config, dry_run=True, log=lambda _line: None)
            installer.run_all()
        finally:
            os.environ["PATH"] = old_path
        self.assertTrue(installer.actions)
        self.assertTrue(any("session" in action or "hook" in action for action in installer.actions))
        self.assertFalse(self.paths.settings.exists())
        self.assertFalse(self.paths.config.exists())

    # --------------------------------------------------------------------- hook

    def test_session_hook_subprocess_never_fails_and_emits_context(self) -> None:
        env = dict(os.environ)
        env["TL_TOOLS_OFFLINE"] = "1"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "session-hook"],
            input="isto não é JSON",
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertTrue(output["additionalContext"].startswith("tl-tools: "))
        self.assertTrue(self.paths.log.exists())

    def test_status_command_json_is_machine_readable(self) -> None:
        env = dict(os.environ)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(set(data["tools"]), set(self.tools.TOOLS))
        self.assertEqual(data["version"], self.tools.VERSION)


if __name__ == "__main__":
    unittest.main()

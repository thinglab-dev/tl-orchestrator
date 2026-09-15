#!/usr/bin/env python3
"""Ferramentas de economia de tokens: instala, verifica e mantém ativas em todo projeto.

Quatro ferramentas externas, todas em escopo de usuário, para que valham em qualquer projeto
sem que ninguém precise lembrar delas:

- rtk (github.com/rtk-ai/rtk): hook `PreToolUse` do Claude Code que reescreve comandos Bash
  para `rtk <cmd>` e devolve a saída condensada; no Codex, instrução global em `AGENTS.md`.
- headroom (github.com/headroomlabs-ai/headroom): proxy local que comprime os resultados de
  ferramentas já admitidos no histórico antes de cada chamada ao modelo, em modo `cache`.
- ponytail (github.com/dietrichgebert/ponytail): plugin que impõe a solução mínima que funciona.
- caveman (github.com/juliusbrussee/caveman): plugin que encurta a prosa sem perder termos
  técnicos, comandos e erros exatos.

Somente biblioteca padrão. `session-hook` nunca falha nem bloqueia uma sessão: sai com 0 sempre.
A política, as evidências e os limites estão em docs/TOKEN_TOOLS.md.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

VERSION = "0.14.0"
TOOLS = ("rtk", "headroom", "ponytail", "caveman")
HARNESSES = ("claude", "codex")
MODES = ("lite", "full", "ultra", "off")
HOOK_TAG = "tl_tools.py"
RTK_HOOK_NEEDLE = "rtk hook claude"
RTK_REPO = "rtk-ai/rtk"
RTK_ASSETS = {
    ("windows", "amd64"): "rtk-x86_64-pc-windows-msvc.zip",
    ("windows", "x86_64"): "rtk-x86_64-pc-windows-msvc.zip",
    ("linux", "x86_64"): "rtk-x86_64-unknown-linux-musl.tar.gz",
    ("linux", "amd64"): "rtk-x86_64-unknown-linux-musl.tar.gz",
    ("linux", "aarch64"): "rtk-aarch64-unknown-linux-gnu.tar.gz",
    ("linux", "arm64"): "rtk-aarch64-unknown-linux-gnu.tar.gz",
    ("darwin", "x86_64"): "rtk-x86_64-apple-darwin.tar.gz",
    ("darwin", "arm64"): "rtk-aarch64-apple-darwin.tar.gz",
    ("darwin", "aarch64"): "rtk-aarch64-apple-darwin.tar.gz",
}
PLUGINS = {
    "ponytail": {"repo": "DietrichGebert/ponytail", "id": "ponytail@ponytail", "marketplace": "ponytail"},
    "caveman": {"repo": "JuliusBrussee/caveman", "id": "caveman@caveman", "marketplace": "caveman"},
}
DEFAULT_CONFIG: dict[str, Any] = {
    "format_version": 1,
    "tools": {"rtk": True, "headroom": True, "ponytail": True, "caveman": True},
    "harnesses": {"claude": True, "codex": True},
    "headroom": {"port": 8790, "mode": "cache", "wait_seconds": 30},
    "modes": {"ponytail": "full", "caveman": "lite"},
    "python_command": "",
}
HOOK_TIMEOUT_SECONDS = 45


# --------------------------------------------------------------------------- caminhos e E/S


@dataclass(frozen=True)
class Paths:
    home: Path
    claude: Path
    codex: Path
    config_dir: Path
    agents_skills: Path
    local_bin: Path

    @classmethod
    def from_env(cls) -> "Paths":
        user_home = Path(os.environ.get("TL_TOOLS_USER_HOME") or Path.home())
        claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or user_home / ".claude")
        codex = Path(os.environ.get("CODEX_HOME") or user_home / ".codex")
        if os.name == "nt":
            config_dir = Path(os.environ.get("APPDATA") or user_home / "AppData" / "Roaming")
        else:
            config_dir = Path(os.environ.get("XDG_CONFIG_HOME") or user_home / ".config")
        home = Path(os.environ.get("TL_TOOLS_HOME") or claude / "tl-tools")
        return cls(
            home=home,
            claude=claude,
            codex=codex,
            config_dir=config_dir,
            agents_skills=user_home / ".agents" / "skills",
            local_bin=user_home / ".local" / "bin",
        )

    @property
    def settings(self) -> Path:
        return self.claude / "settings.json"

    @property
    def config(self) -> Path:
        return self.home / "config.json"

    @property
    def state(self) -> Path:
        return self.home / "state.json"

    @property
    def log(self) -> Path:
        return self.home / "session-hook.log"

    @property
    def proxy_log(self) -> Path:
        return self.home / "headroom-proxy.log"

    @property
    def proxy_pid(self) -> Path:
        return self.home / "headroom-proxy.pid"

    def tool_config(self, tool: str) -> Path:
        return self.config_dir / tool / "config.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def append_log(path: Path, line: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 200_000:
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + line.rstrip() + "\n")
    except OSError:
        pass


def load_config(paths: Paths) -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    stored = load_json(paths.config, {})
    if isinstance(stored, dict):
        for key, value in stored.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config


def which(name: str, paths: Paths | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if paths is not None:
        for candidate in (paths.local_bin / name, paths.local_bin / f"{name}.exe"):
            if candidate.is_file():
                return str(candidate)
    return None


def run(cmd: list[str], timeout: int = 300, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.DEVNULL,
    )


def store_python(executable: str | None = None) -> bool:
    """Python da Microsoft Store: seus filhos herdam a virtualização de AppData e não enxergam
    os launchers do uv (`uv trampoline failed to canonicalize script path`)."""
    return os.name == "nt" and "windowsapps" in (executable or sys.executable).lower()


def clean_python() -> str | None:
    """Interpretador fora do pacote da Store, para lançar processos que precisam de AppData real."""
    if os.name != "nt":
        return None
    override = os.environ.get("TL_TOOLS_PYTHON")
    if override and Path(override).is_file():
        return override
    roots = [
        Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Programs" / "Python",
        Path(os.environ.get("ProgramFiles") or r"C:\Program Files"),
    ]
    for root in roots:
        if root.is_dir():
            for candidate in sorted(root.glob("Python3*/python.exe"), reverse=True):
                if not store_python(str(candidate)):
                    return str(candidate)
    return None


def python_command(config: dict[str, Any]) -> str:
    configured = str(config.get("python_command") or "").strip()
    if configured:
        return configured
    found = shutil.which("python")
    if found and store_python(found):
        clean = clean_python()
        if clean:
            return f'"{Path(clean).as_posix()}"'
    if found:
        return "python"
    if shutil.which("python3"):
        return "python3"
    return f'"{Path(sys.executable).as_posix()}"'


# --------------------------------------------------------------------------- settings do Claude


def read_settings(paths: Paths) -> dict[str, Any]:
    data = load_json(paths.settings, {})
    return data if isinstance(data, dict) else {}


def write_settings(paths: Paths, settings: dict[str, Any]) -> None:
    save_json(paths.settings, settings)


def hook_entries(settings: dict[str, Any], event: str) -> list[dict[str, Any]]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    entries = hooks.get(event)
    return entries if isinstance(entries, list) else []


def hook_present(settings: dict[str, Any], event: str, needle: str) -> bool:
    for group in hook_entries(settings, event):
        for hook in group.get("hooks", []) if isinstance(group, dict) else []:
            if isinstance(hook, dict) and needle in str(hook.get("command", "")):
                return True
    return False


def add_hook(settings: dict[str, Any], event: str, matcher: str | None, command: str, timeout: int) -> bool:
    """Adiciona o hook uma única vez; devolve True quando alterou o objeto."""
    if hook_present(settings, event, command):
        return False
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = settings["hooks"] = {}
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        groups = hooks[event] = []
    group: dict[str, Any] = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
    if matcher:
        group["matcher"] = matcher
    groups.append(group)
    return True


def remove_hook(settings: dict[str, Any], event: str, needle: str) -> bool:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get(event), list):
        return False
    changed = False
    kept_groups = []
    for group in hooks[event]:
        if not isinstance(group, dict):
            kept_groups.append(group)
            continue
        kept = [h for h in group.get("hooks", []) if not (isinstance(h, dict) and needle in str(h.get("command", "")))]
        if len(kept) != len(group.get("hooks", [])):
            changed = True
        if kept:
            group = dict(group)
            group["hooks"] = kept
            kept_groups.append(group)
    hooks[event] = kept_groups
    if not kept_groups:
        del hooks[event]
    if not hooks:
        del settings["hooks"]
    return changed


def get_env(settings: dict[str, Any], key: str) -> str | None:
    env = settings.get("env")
    if isinstance(env, dict) and key in env:
        return str(env[key])
    return None


def set_env(settings: dict[str, Any], key: str, value: str) -> bool:
    env = settings.setdefault("env", {})
    if not isinstance(env, dict):
        env = settings["env"] = {}
    if env.get(key) == value:
        return False
    env[key] = value
    return True


def unset_env(settings: dict[str, Any], key: str) -> bool:
    env = settings.get("env")
    if isinstance(env, dict) and key in env:
        del env[key]
        if not env:
            del settings["env"]
        return True
    return False


def plugin_enabled(settings: dict[str, Any], plugin_id: str) -> bool:
    enabled = settings.get("enabledPlugins")
    return isinstance(enabled, dict) and enabled.get(plugin_id) is True


def plugin_cached(paths: Paths, tool: str) -> bool:
    spec = PLUGINS[tool]
    root = paths.claude / "plugins" / "cache" / spec["marketplace"] / tool
    return root.is_dir() and any(child.is_dir() for child in root.iterdir())


# --------------------------------------------------------------------------- modos ponytail/caveman


MODE_ENV = {"ponytail": "PONYTAIL_DEFAULT_MODE", "caveman": "CAVEMAN_DEFAULT_MODE"}


def read_mode(paths: Paths, tool: str) -> str | None:
    """Modo padrão configurado: env do settings do Claude, env do processo, depois o config.json.

    O `env` do settings é a fonte durável: os hooks dos plugins herdam essas variáveis em toda
    sessão, e ela não depende de escrita em AppData, que o Python da Microsoft Store redireciona
    para uma pasta virtual invisível ao Node.
    """
    candidates = (get_env(read_settings(paths), MODE_ENV[tool]), os.environ.get(MODE_ENV[tool]))
    for value in candidates:
        if isinstance(value, str) and value.strip().lower() in MODES:
            return value.strip().lower()
    data = load_json(paths.tool_config(tool), {})
    mode = data.get("defaultMode") if isinstance(data, dict) else None
    return mode.lower() if isinstance(mode, str) and mode.lower() in MODES else None


def caveman_flag_path(paths: Paths) -> Path:
    return paths.claude / ".caveman-active"


def caveman_flag_mode(paths: Paths) -> str | None:
    value = read_text(caveman_flag_path(paths)).strip().lower()
    return value if value in MODES else None


def effective_mode(paths: Paths, tool: str) -> str | None:
    """Modo que uma sessão nova recebe: o caveman herda o flag legado antes da configuração."""
    if tool == "caveman":
        flag = caveman_flag_mode(paths)
        if flag:
            return flag
    return read_mode(paths, tool)


def write_mode(paths: Paths, tool: str, mode: str) -> bool:
    if mode not in MODES:
        raise ValueError(f"modo inválido para {tool}: {mode}")
    changed = False
    settings = read_settings(paths)
    if set_env(settings, MODE_ENV[tool], mode):
        write_settings(paths, settings)
        changed = True
    path = paths.tool_config(tool)
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}
    if data.get("defaultMode") != mode:
        data["defaultMode"] = mode
        try:
            save_json(path, data)  # melhor esforço: cobre harness que só lê o config.json
            changed = True
        except OSError:
            pass
    if tool == "caveman" and caveman_flag_mode(paths) != mode:
        # O hook do caveman lê este flag antes da configuração; sem sincronizá-lo, um modo
        # antigo fica colado em todas as sessões seguintes.
        try:
            caveman_flag_path(paths).parent.mkdir(parents=True, exist_ok=True)
            caveman_flag_path(paths).write_text(mode, encoding="utf-8")
            changed = True
        except OSError:
            pass
    return changed


# --------------------------------------------------------------------------- Codex: bloco gerenciado

CODEX_BLOCK_START = "<!-- tl-tools:start -->"
CODEX_BLOCK_END = "<!-- tl-tools:end -->"


def codex_block_text(paths: Paths, config: dict[str, Any]) -> str:
    lines = [CODEX_BLOCK_START, "## Economia de tokens (tl-orchestrator)", ""]
    ponytail_mode = str(config["modes"].get("ponytail", "full"))
    caveman_mode = str(config["modes"].get("caveman", "lite"))
    if config["tools"].get("ponytail") and ponytail_mode != "off":
        lines.append(
            f"- Em toda tarefa de código, aplique a skill `ponytail` no nível `{ponytail_mode}`: a solução mínima que"
            " cumpre o pedido, biblioteca padrão e recursos nativos antes de dependências, sem abstrações não"
            " pedidas; nunca corte validação, tratamento de erro, segurança ou acessibilidade."
        )
    if config["tools"].get("caveman") and caveman_mode != "off":
        lines.append(
            f"- Nas respostas, aplique a skill `caveman` no nível `{caveman_mode}`: sem enrolação nem hedging,"
            " frases completas, termos técnicos, comandos, caminhos e erros exatos preservados."
        )
    if config["tools"].get("rtk"):
        rtk = which("rtk", paths)
        if rtk:
            lines.append(f"- Se `rtk` não estiver no PATH, use o caminho completo `{Path(rtk).as_posix()}` com o mesmo prefixo.")
    if len(lines) == 3:
        return ""
    lines.append(CODEX_BLOCK_END)
    return "\n".join(lines) + "\n"


def codex_block_present(paths: Paths, tool: str) -> bool:
    text = read_text(paths.codex / "AGENTS.md")
    if CODEX_BLOCK_START not in text or CODEX_BLOCK_END not in text:
        return False
    block = text.split(CODEX_BLOCK_START, 1)[1].split(CODEX_BLOCK_END, 1)[0]
    return f"`{tool}`" in block


def write_codex_block(paths: Paths, config: dict[str, Any]) -> bool:
    path = paths.codex / "AGENTS.md"
    text = read_text(path)
    wanted = codex_block_text(paths, config)
    if CODEX_BLOCK_START in text and CODEX_BLOCK_END in text:
        head, rest = text.split(CODEX_BLOCK_START, 1)
        _old, tail = rest.split(CODEX_BLOCK_END, 1)
        new_text = head + wanted + tail.lstrip("\n") if wanted else head.rstrip("\n") + "\n" + tail.lstrip("\n")
    else:
        if not wanted:
            return False
        new_text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + wanted
    if new_text == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- headroom


def headroom_executable(paths: Paths) -> str | None:
    override = os.environ.get("TL_TOOLS_HEADROOM_EXE")
    if override and Path(override).is_file():
        return override
    tool_dir = Path(os.environ.get("UV_TOOL_DIR") or "")
    if not tool_dir.name:
        if os.name == "nt":
            tool_dir = paths.config_dir / "uv" / "tools"
        else:
            tool_dir = Path.home() / ".local" / "share" / "uv" / "tools"
    for candidate in (
        tool_dir / "headroom-ai" / "Scripts" / "headroom.exe",
        tool_dir / "headroom-ai" / "bin" / "headroom",
    ):
        if candidate.is_file():
            return str(candidate)
    return which("headroom", paths)


def proxy_url(config: dict[str, Any]) -> str:
    return f"http://127.0.0.1:{int(config['headroom']['port'])}"


def proxy_health(url: str, timeout: float = 1.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        if isinstance(data, dict) and data.get("service") == "headroom-proxy":
            return data
    except (urllib.error.URLError, ValueError, OSError):
        return None
    return None


def proxy_start(paths: Paths, config: dict[str, Any]) -> int | None:
    exe = headroom_executable(paths)
    if not exe:
        return None
    paths.home.mkdir(parents=True, exist_ok=True)
    if store_python():
        # Um filho do Python da Store não consegue rodar o launcher do uv; delega o lançamento
        # ao interpretador limpo, que executa este mesmo comando fora da virtualização.
        clean = clean_python()
        if clean:
            try:
                run([clean, str(Path(__file__).resolve()), "proxy", "start"], timeout=180)
            except (OSError, subprocess.SubprocessError):
                return None
            raw = read_text(paths.proxy_pid).strip()
            return int(raw) if raw.isdigit() else None
    cmd = [exe, "proxy", "--port", str(int(config["headroom"]["port"])), "--mode", str(config["headroom"]["mode"]), "--no-telemetry"]
    log = open(paths.proxy_log, "ab")
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | 0x08000000
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(cmd, **kwargs)
    except OSError:
        return None
    finally:
        log.close()
    try:
        paths.proxy_pid.write_text(str(process.pid), encoding="utf-8")
    except OSError:
        pass
    return process.pid


def proxy_ensure(paths: Paths, config: dict[str, Any], wait_seconds: int | None = None) -> tuple[bool, bool, str]:
    """Garante o proxy no ar. Devolve (saudável, iniciado agora, detalhe)."""
    url = proxy_url(config)
    if proxy_health(url):
        return True, False, "já estava no ar"
    if os.environ.get("TL_TOOLS_OFFLINE"):
        return False, False, "modo offline"
    pid = proxy_start(paths, config)
    if pid is None:
        return False, False, "executável do headroom não encontrado ou não iniciou"
    budget = int(config["headroom"].get("wait_seconds", 30) if wait_seconds is None else wait_seconds)
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if proxy_health(url):
            return True, True, f"iniciado agora (pid {pid})"
        time.sleep(0.5)
    return False, True, f"iniciado (pid {pid}) mas não respondeu em {budget}s"


def listener_pids(port: int) -> list[int]:
    """PIDs que escutam a porta local, para parar um proxy iniciado fora deste script."""
    pids: list[int] = []
    try:
        if os.name == "nt":
            out = run(["netstat", "-ano", "-p", "TCP"], timeout=30).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING" and parts[4].isdigit():
                    pids.append(int(parts[4]))
        else:
            out = run(["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"], timeout=30).stdout
            pids = [int(p) for p in out.split() if p.strip().isdigit()]
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted(set(pids))


def kill_pid(pid: int) -> None:
    if os.name == "nt":
        run(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=30)
    else:
        import signal

        os.kill(pid, signal.SIGTERM)


def proxy_stop(paths: Paths, config: dict[str, Any] | None = None) -> str:
    """Encerra o proxy: o pid registrado e todo processo que escute a porta, até o /health cair."""
    raw = read_text(paths.proxy_pid).strip()
    targets = [int(raw)] if raw.isdigit() else []
    port = int(config["headroom"]["port"]) if config is not None else None
    if port is not None:
        targets += listener_pids(port)
    if not targets:
        return "sem pid registrado e nada escutando na porta"
    killed: list[int] = []
    for _round in range(3):
        for pid in sorted(set(targets)):
            try:
                kill_pid(pid)
                killed.append(pid)
            except (OSError, subprocess.SubprocessError):
                pass
        if port is None:
            break
        time.sleep(1.0)
        targets = listener_pids(port)
        if not targets and not proxy_health(f"http://127.0.0.1:{port}"):
            break
    try:
        paths.proxy_pid.unlink()
    except OSError:
        pass
    return f"pids encerrados: {', '.join(str(p) for p in sorted(set(killed)))}"


# --------------------------------------------------------------------------- estado


def codex_present(paths: Paths) -> bool:
    return paths.codex.is_dir() or shutil.which("codex") is not None


def codex_config_text(paths: Paths) -> str:
    return read_text(paths.codex / "config.toml")


def codex_plugin_enabled(paths: Paths, plugin_id: str) -> bool:
    text = codex_config_text(paths)
    match = re.search(r'\[plugins\."' + re.escape(plugin_id) + r'"\]\s*\n(?:\s*enabled\s*=\s*(true|false))?', text)
    return bool(match) and match.group(1) != "false"


def caveman_codex_skill(paths: Paths) -> bool:
    return any((base / "caveman" / "SKILL.md").is_file() for base in (paths.agents_skills, paths.codex / "skills"))


def collect_status(paths: Paths, config: dict[str, Any], probe_proxy: bool = True) -> dict[str, Any]:
    settings = read_settings(paths)
    url = proxy_url(config)
    health = proxy_health(url) if probe_proxy else None
    routed_here = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/") == url
    codex_on = bool(config["harnesses"].get("codex")) and codex_present(paths)
    status: dict[str, Any] = {
        "version": VERSION,
        "home": str(paths.home),
        "hook": hook_present(settings, "SessionStart", HOOK_TAG),
        "codex_present": codex_present(paths),
        "tools": {},
    }
    rtk_exe = which("rtk", paths)
    status["tools"]["rtk"] = {
        "enabled": bool(config["tools"].get("rtk")),
        "installed": rtk_exe is not None,
        "path": rtk_exe,
        "claude": hook_present(settings, "PreToolUse", RTK_HOOK_NEEDLE),
        "codex": ("RTK.md" in read_text(paths.codex / "AGENTS.md")) if codex_on else None,
    }
    hr_exe = headroom_executable(paths)
    status["tools"]["headroom"] = {
        "enabled": bool(config["tools"].get("headroom")),
        "installed": hr_exe is not None,
        "path": hr_exe,
        "url": url,
        "mode": str(config["headroom"]["mode"]),
        "proxy": health is not None,
        "proxy_version": health.get("version") if isinstance(health, dict) else None,
        "claude": get_env(settings, "ANTHROPIC_BASE_URL") == url,
        "routed_this_session": routed_here,
        "codex": ("headroom" in codex_config_text(paths).lower()) if codex_on else None,
    }
    for tool in ("ponytail", "caveman"):
        spec = PLUGINS[tool]
        entry: dict[str, Any] = {
            "enabled": bool(config["tools"].get(tool)),
            "installed": plugin_cached(paths, tool),
            "claude": plugin_enabled(settings, spec["id"]) and plugin_cached(paths, tool),
            "mode": effective_mode(paths, tool),
            "wanted_mode": str(config["modes"].get(tool)),
        }
        if tool == "ponytail":
            entry["codex"] = (codex_plugin_enabled(paths, spec["id"]) and codex_block_present(paths, tool)) if codex_on else None
        else:
            entry["codex"] = (caveman_codex_skill(paths) and codex_block_present(paths, tool)) if codex_on else None
        status["tools"][tool] = entry
    return status


def tool_active(entry: dict[str, Any], tool: str) -> bool:
    if not entry.get("enabled"):
        return False
    if tool == "rtk":
        return bool(entry["installed"] and entry["claude"])
    if tool == "headroom":
        return bool(entry["installed"] and entry["proxy"] and entry["claude"])
    return bool(entry["claude"] and entry.get("mode") not in (None, "off"))


def brief_line(status: dict[str, Any]) -> str:
    parts = []
    tools = status["tools"]
    rtk = tools["rtk"]
    if rtk["enabled"]:
        parts.append("rtk ok (saída Bash condensada; `rtk proxy <cmd>` devolve o bruto)" if tool_active(rtk, "rtk") else "rtk INATIVO")
    hr = tools["headroom"]
    if hr["enabled"]:
        if tool_active(hr, "headroom"):
            where = "roteado nesta sessão" if hr["routed_this_session"] else "só sessões CLI; esta não passa pelo proxy"
            parts.append(f"headroom ok :{hr['url'].rsplit(':', 1)[1]} {hr['mode']} ({where})")
        else:
            parts.append("headroom INATIVO")
    for tool in ("ponytail", "caveman"):
        entry = tools[tool]
        if entry["enabled"]:
            parts.append(f"{tool} {entry['mode']}" if tool_active(entry, tool) else f"{tool} INATIVO")
    if not parts:
        parts.append("todas as ferramentas desligadas na configuração")
    return "tl-tools: " + " | ".join(parts)


def print_status(status: dict[str, Any]) -> None:
    print(brief_line(status))
    print(f"  hook de sessão: {'registrado' if status['hook'] else 'AUSENTE'}   home: {status['home']}")
    for tool, entry in status["tools"].items():
        flag = "on " if entry["enabled"] else "off"
        claude = "ok" if entry["claude"] else "--"
        codex = "n/a" if entry.get("codex") is None else ("ok" if entry["codex"] else "--")
        extra = ""
        if tool == "headroom":
            extra = f" proxy={'ok' if entry['proxy'] else '--'} url={entry['url']}"
        if tool in ("ponytail", "caveman"):
            extra = f" modo={entry['mode']} (desejado {entry['wanted_mode']})"
        print(f"  [{flag}] {tool:9} instalado={'sim' if entry['installed'] else 'não'} claude={claude} codex={codex}{extra}")


# --------------------------------------------------------------------------- instalação


class Installer:
    def __init__(self, paths: Paths, config: dict[str, Any], dry_run: bool, log: Callable[[str], None]) -> None:
        self.paths = paths
        self.config = config
        self.dry_run = dry_run
        self.log = log
        self.actions: list[str] = []
        self.problems: list[str] = []

    def exec(self, cmd: list[str], timeout: int = 600, ignore_failure: bool = False) -> bool:
        shown = " ".join(cmd)
        self.actions.append(shown)
        if self.dry_run:
            self.log(f"[dry-run] {shown}")
            return True
        self.log(f"$ {shown}")
        try:
            result = run(cmd, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            self.problems.append(f"{shown}: {exc}")
            return False
        if result.returncode != 0 and not ignore_failure:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
            self.problems.append(f"{shown}: exit {result.returncode} {' / '.join(tail)}")
            return False
        return True

    # rtk -------------------------------------------------------------------
    def install_rtk(self) -> None:
        paths, config = self.paths, self.config
        if not which("rtk", paths):
            self.download_rtk()
        exe = which("rtk", paths)
        if not exe:
            self.problems.append("rtk: binário não disponível")
            return
        settings = read_settings(paths)
        if not hook_present(settings, "PreToolUse", RTK_HOOK_NEEDLE):
            self.exec([exe, "init", "-g", "--auto-patch"])
        if config["harnesses"].get("codex") and codex_present(paths) and "RTK.md" not in read_text(paths.codex / "AGENTS.md"):
            self.exec([exe, "init", "-g", "--codex"])

    def download_rtk(self) -> None:
        asset = rtk_asset_name()
        if not asset:
            self.problems.append(f"rtk: plataforma sem ativo conhecido ({platform.system()} {platform.machine()})")
            return
        self.actions.append(f"download github.com/{RTK_REPO} {asset} -> {self.paths.local_bin}")
        if self.dry_run:
            self.log(f"[dry-run] baixar {asset}")
            return
        try:
            with urllib.request.urlopen(f"https://api.github.com/repos/{RTK_REPO}/releases/latest", timeout=30) as response:
                release = json.loads(response.read().decode("utf-8"))
            url = next(a["browser_download_url"] for a in release["assets"] if a["name"] == asset)
            with urllib.request.urlopen(url, timeout=120) as response:
                blob = response.read()
        except (urllib.error.URLError, OSError, ValueError, StopIteration, KeyError) as exc:
            self.problems.append(f"rtk: download falhou: {exc}")
            return
        self.paths.local_bin.mkdir(parents=True, exist_ok=True)
        name = "rtk.exe" if os.name == "nt" else "rtk"
        try:
            if asset.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    member = next(m for m in archive.namelist() if m.endswith(name))
                    (self.paths.local_bin / name).write_bytes(archive.read(member))
            else:
                with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
                    member = next(m for m in archive.getmembers() if m.name.endswith(name) and m.isfile())
                    extracted = archive.extractfile(member)
                    (self.paths.local_bin / name).write_bytes(extracted.read() if extracted else b"")
            if os.name != "nt":
                os.chmod(self.paths.local_bin / name, 0o755)
        except (OSError, StopIteration, zipfile.BadZipFile, tarfile.TarError) as exc:
            self.problems.append(f"rtk: extração falhou: {exc}")
            return
        self.log(f"rtk instalado em {self.paths.local_bin / name} ({release.get('tag_name')})")
        if str(self.paths.local_bin) not in os.environ.get("PATH", ""):
            self.problems.append(f"rtk: acrescente {self.paths.local_bin} ao PATH do usuário para o hook encontrá-lo")

    # headroom ----------------------------------------------------------------
    def install_headroom(self) -> None:
        paths, config = self.paths, self.config
        if not headroom_executable(paths):
            if shutil.which("uv"):
                self.exec(["uv", "tool", "install", "--python", "3.13", "headroom-ai[proxy]"], timeout=1800)
            else:
                self.exec([sys.executable, "-m", "pip", "install", "--user", "headroom-ai[proxy]"], timeout=1800)
        if not headroom_executable(paths):
            self.problems.append("headroom: executável não encontrado após a instalação")
            return
        if self.dry_run:
            self.actions.append(f"garantir proxy em {proxy_url(config)} e gravar ANTHROPIC_BASE_URL em {paths.settings}")
            return
        healthy, _started, detail = proxy_ensure(paths, config)
        self.log(f"headroom proxy: {detail}")
        if not healthy:
            self.problems.append(f"headroom: proxy não subiu ({detail}); Claude não foi roteado")
            return
        settings = read_settings(paths)
        current = get_env(settings, "ANTHROPIC_BASE_URL")
        url = proxy_url(config)
        if current and current != url and "127.0.0.1" not in current and "localhost" not in current:
            self.problems.append(f"headroom: ANTHROPIC_BASE_URL já aponta para {current}; não sobrescrito")
            return
        if set_env(settings, "ANTHROPIC_BASE_URL", url):
            write_settings(paths, settings)
            self.log(f"ANTHROPIC_BASE_URL={url} gravado em {paths.settings}")

    # plugins -----------------------------------------------------------------
    def install_plugin(self, tool: str) -> None:
        paths, config = self.paths, self.config
        spec = PLUGINS[tool]
        claude = shutil.which("claude")
        settings = read_settings(paths)
        if not (plugin_enabled(settings, spec["id"]) and plugin_cached(paths, tool)):
            if not claude:
                self.problems.append(f"{tool}: comando `claude` não encontrado para instalar o plugin")
            else:
                self.exec([claude, "plugin", "marketplace", "add", spec["repo"]], ignore_failure=True)
                self.exec([claude, "plugin", "install", spec["id"]])
        wanted = str(config["modes"].get(tool))
        # Sempre reafirma o modo: o config.json pode ser uma cópia virtual (Python da Store) que
        # só este processo enxerga, e o `env` do settings é o que os hooks dos plugins leem.
        self.actions.append(f"gravar {MODE_ENV[tool]}={wanted} no settings e defaultMode em {paths.tool_config(tool)}")
        if not self.dry_run:
            write_mode(paths, tool, wanted)
        if config["harnesses"].get("codex") and codex_present(paths):
            self.install_plugin_codex(tool)
            self.sync_codex_block()

    def sync_codex_block(self) -> None:
        if not codex_present(self.paths):
            return
        if self.dry_run:
            self.actions.append(f"sincronizar bloco tl-tools em {self.paths.codex / 'AGENTS.md'}")
            return
        if write_codex_block(self.paths, self.config):
            self.log(f"bloco tl-tools gravado em {self.paths.codex / 'AGENTS.md'}")

    def install_plugin_codex(self, tool: str) -> None:
        paths = self.paths
        spec = PLUGINS[tool]
        if tool == "ponytail":
            if codex_plugin_enabled(paths, spec["id"]):
                return
            codex = shutil.which("codex")
            if not codex:
                self.problems.append("ponytail: comando `codex` não encontrado")
                return
            self.exec([codex, "plugin", "marketplace", "add", spec["repo"]], ignore_failure=True)
            self.exec([codex, "plugin", "add", spec["id"]])
            return
        if caveman_codex_skill(paths):
            return
        npx = shutil.which("npx")
        if not npx:
            self.problems.append("caveman: `npx` não encontrado para instalar a skill no Codex")
            return
        self.exec([npx, "-y", "skills", "add", spec["repo"], "--skill", "*", "-a", "codex", "--yes", "-g"], timeout=900)

    # próprio hook ------------------------------------------------------------
    def install_self(self) -> None:
        paths, config = self.paths, self.config
        target = paths.home / "tl_tools.py"
        source = Path(__file__).resolve()
        same_file = target.exists() and source == target.resolve()
        if not same_file and (not target.exists() or target.read_bytes() != source.read_bytes()):
            self.actions.append(f"copiar {source} -> {target}")
            if not self.dry_run:
                paths.home.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        if not paths.config.exists():
            self.actions.append(f"gravar configuração padrão em {paths.config}")
            if not self.dry_run:
                save_json(paths.config, config)
        command = f'{python_command(config)} "{target.as_posix()}" session-hook'
        settings = read_settings(paths)
        if not hook_present(settings, "SessionStart", command):
            self.actions.append(f"registrar hook SessionStart em {paths.settings}")
            if not self.dry_run:
                remove_hook(settings, "SessionStart", HOOK_TAG)
                add_hook(settings, "SessionStart", "startup|resume|clear|compact", command, HOOK_TIMEOUT_SECONDS)
                write_settings(paths, settings)

    def run_all(self, only: set[str] | None = None) -> None:
        for tool in TOOLS:
            if not self.config["tools"].get(tool) or (only and tool not in only):
                continue
            self.log(f"== {tool}")
            if tool == "rtk":
                self.install_rtk()
            elif tool == "headroom":
                self.install_headroom()
            else:
                self.install_plugin(tool)
        if not only or "self" in only:
            self.log("== hook de sessão")
            self.install_self()


def rtk_asset_name() -> str | None:
    return RTK_ASSETS.get((platform.system().lower(), platform.machine().lower()))


# --------------------------------------------------------------------------- hook de sessão


def session_hook(paths: Paths, config: dict[str, Any]) -> dict[str, Any]:
    """Executa em toda sessão nova: garante o proxy e devolve uma linha de contexto."""
    started = time.monotonic()
    notes: list[str] = []
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        payload = {}
    if config["tools"].get("headroom") and headroom_executable(paths):
        settings = read_settings(paths)
        routed = get_env(settings, "ANTHROPIC_BASE_URL") == proxy_url(config)
        budget = min(int(config["headroom"].get("wait_seconds", 30)), HOOK_TIMEOUT_SECONDS - 10)
        healthy, started_now, detail = proxy_ensure(paths, config, wait_seconds=budget)
        if started_now:
            notes.append(f"headroom proxy {detail}")
        if not healthy and routed:
            # Falha aberta: sessões futuras deixam de apontar para um proxy morto.
            unset_env(settings, "ANTHROPIC_BASE_URL")
            write_settings(paths, settings)
            notes.append("headroom indisponível; ANTHROPIC_BASE_URL removido do settings para as próximas sessões")
    for tool in ("ponytail", "caveman"):
        if not config["tools"].get(tool):
            continue
        wanted = str(config["modes"].get(tool, "off"))
        if wanted not in MODES:
            continue
        settings = read_settings(paths)
        if get_env(settings, MODE_ENV[tool]) != wanted or (tool == "caveman" and caveman_flag_mode(paths) not in (None, wanted)):
            # Sessão nova volta ao modo da política; a troca por `/caveman` vale só na sessão.
            try:
                if write_mode(paths, tool, wanted):
                    notes.append(f"{tool} devolvido a {wanted}")
            except (OSError, ValueError):
                pass
    status = collect_status(paths, config, probe_proxy=True)
    line = brief_line(status)
    if not status["hook"]:
        notes.append("hook de sessão não registrado no settings")
    if notes:
        line += " | " + "; ".join(notes)
    elapsed = time.monotonic() - started
    append_log(paths.log, f"{payload.get('source', payload.get('hook_event_name', '?'))} {elapsed:.1f}s {line}")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": line}}


# --------------------------------------------------------------------------- doctor


def doctor(paths: Paths, config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    status = collect_status(paths, config, probe_proxy=True)
    warnings: list[str] = []
    for tool in TOOLS:
        entry = status["tools"][tool]
        if entry["enabled"] and not tool_active(entry, tool):
            warnings.append(f"{tool}: ligado na configuração mas inativo no Claude Code")
        if entry["enabled"] and entry.get("codex") is False and tool != "headroom":
            # headroom no Codex é opt-in manual por política (docs/TOKEN_TOOLS.md).
            warnings.append(f"{tool}: não configurado no Codex")
        if tool in ("ponytail", "caveman") and entry["enabled"] and entry["mode"] not in (None, entry["wanted_mode"]):
            warnings.append(f"{tool}: modo atual {entry['mode']} difere do desejado {entry['wanted_mode']}")
    if not status["hook"]:
        warnings.append("hook SessionStart do tl-tools não registrado")
    if config["tools"].get("rtk") and not shutil.which("rg"):
        warnings.append("rtk: `rg` (ripgrep) ausente do PATH; alguns filtros avisam")
    if (config["tools"].get("ponytail") or config["tools"].get("caveman")) and not shutil.which("node"):
        warnings.append("ponytail/caveman: `node` ausente do PATH; os hooks dos plugins ficam mudos")
    if str(paths.local_bin) not in os.environ.get("PATH", "") and status["tools"]["rtk"]["path"] and str(paths.local_bin) in str(status["tools"]["rtk"]["path"]):
        warnings.append(f"rtk: {paths.local_bin} fora do PATH; o hook `rtk hook claude` pode não encontrá-lo")
    versions: dict[str, str] = {}
    rtk_exe = status["tools"]["rtk"]["path"]
    if rtk_exe:
        try:
            result = run([rtk_exe, "--version"], timeout=60)
            versions["rtk"] = ((result.stdout or result.stderr).strip().splitlines() or ["?"])[0]
        except (OSError, subprocess.SubprocessError):
            versions["rtk"] = "?"
    if status["tools"]["headroom"]["installed"]:
        # O launcher do headroom não responde a um filho do Python da Store; o /health já traz a versão.
        versions["headroom"] = status["tools"]["headroom"].get("proxy_version") or "? (proxy fora do ar)"
    if store_python() and not clean_python():
        warnings.append("Python da Microsoft Store sem interpretador limpo em Programs\\Python; o proxy do headroom não pode ser iniciado por este script")
    status["versions"] = versions
    return status, warnings


# --------------------------------------------------------------------------- CLI


def cmd_status(args: argparse.Namespace, paths: Paths, config: dict[str, Any]) -> int:
    status = collect_status(paths, config)
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif args.brief:
        print(brief_line(status))
    else:
        print_status(status)
    return 0


def cmd_doctor(args: argparse.Namespace, paths: Paths, config: dict[str, Any]) -> int:
    if args.fix:
        installer = Installer(paths, config, dry_run=False, log=print)
        installer.run_all()
        for problem in installer.problems:
            print(f"problema: {problem}")
    status, warnings = doctor(paths, config)
    if args.json:
        status["warnings"] = warnings
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print_status(status)
        for tool, version in status.get("versions", {}).items():
            print(f"  versão {tool}: {version}")
        for warning in warnings:
            print(f"  aviso: {warning}")
        print("  resultado: " + ("tudo ativo" if not warnings else f"{len(warnings)} aviso(s)"))
    return 1 if warnings else 0


def cmd_install(args: argparse.Namespace, paths: Paths, config: dict[str, Any]) -> int:
    only = set(args.only.split(",")) if args.only else None
    installer = Installer(paths, config, dry_run=args.dry_run, log=print)
    installer.run_all(only)
    if args.dry_run:
        print("ações planejadas:")
        for action in installer.actions:
            print(f"  - {action}")
    for problem in installer.problems:
        print(f"problema: {problem}")
    if not args.dry_run:
        state = load_json(paths.state, {})
        if not isinstance(state, dict):
            state = {}
        state["last_install"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "actions": installer.actions, "problems": installer.problems}
        save_json(paths.state, state)
        print_status(collect_status(paths, config))
    return 1 if installer.problems else 0


def cmd_enable(args: argparse.Namespace, paths: Paths, config: dict[str, Any], enable: bool) -> int:
    tool = args.tool
    config["tools"][tool] = enable
    save_json(paths.config, config)
    settings = read_settings(paths)
    if enable:
        installer = Installer(paths, config, dry_run=False, log=print)
        installer.run_all({tool})
        for problem in installer.problems:
            print(f"problema: {problem}")
        if tool in ("ponytail", "caveman"):
            write_mode(paths, tool, str(config["modes"][tool]))
        return 1 if installer.problems else 0
    if tool == "rtk":
        if remove_hook(settings, "PreToolUse", RTK_HOOK_NEEDLE):
            write_settings(paths, settings)
            print("hook do rtk removido do settings (binário e RTK.md preservados)")
    elif tool == "headroom":
        if unset_env(settings, "ANTHROPIC_BASE_URL"):
            write_settings(paths, settings)
            print("ANTHROPIC_BASE_URL removido do settings")
        print(f"proxy: {proxy_stop(paths, config)}")
    else:
        write_mode(paths, tool, "off")
        print(f"{tool}: defaultMode=off gravado (plugin permanece instalado; `/{tool} full` religa por sessão)")
    if codex_present(paths) and write_codex_block(paths, config):
        print(f"bloco tl-tools atualizado em {paths.codex / 'AGENTS.md'}")
    return 0


def cmd_set_mode(args: argparse.Namespace, paths: Paths, config: dict[str, Any]) -> int:
    config["modes"][args.tool] = args.mode
    save_json(paths.config, config)
    write_mode(paths, args.tool, args.mode)
    print(f"{args.tool}: defaultMode={args.mode}")
    if codex_present(paths) and write_codex_block(paths, config):
        print(f"bloco tl-tools atualizado em {paths.codex / 'AGENTS.md'}")
    return 0


def cmd_proxy(args: argparse.Namespace, paths: Paths, config: dict[str, Any]) -> int:
    if args.action == "status":
        health = proxy_health(proxy_url(config))
        print(json.dumps(health or {"status": "down", "url": proxy_url(config)}, indent=2)[:1200])
        return 0 if health else 1
    if args.action == "stop":
        print(proxy_stop(paths, config))
        return 0
    healthy, started, detail = proxy_ensure(paths, config)
    print(f"{'ok' if healthy else 'falha'}: {detail}")
    return 0 if healthy else 1


def cmd_session_hook(_args: argparse.Namespace, paths: Paths, config: dict[str, Any]) -> int:
    try:
        output = session_hook(paths, config)
    except Exception as exc:  # noqa: BLE001 - o hook nunca pode derrubar a sessão
        append_log(paths.log, f"erro no hook: {exc!r}")
        output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": f"tl-tools: hook falhou ({exc.__class__.__name__}); ferramentas podem estar inativas"}}
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tl_tools.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"tl_tools {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="estado das ferramentas sem efeitos colaterais")
    status.add_argument("--json", action="store_true")
    status.add_argument("--brief", action="store_true")

    doc = sub.add_parser("doctor", help="diagnóstico com sondas reais; exit 1 se algo inativo")
    doc.add_argument("--json", action="store_true")
    doc.add_argument("--fix", action="store_true", help="instala o que faltar antes de diagnosticar")

    inst = sub.add_parser("install", help="instala e configura tudo que estiver ligado (idempotente)")
    inst.add_argument("--only", help="lista separada por vírgula: rtk,headroom,ponytail,caveman,self")
    inst.add_argument("--dry-run", action="store_true")

    en = sub.add_parser("enable", help="liga uma ferramenta e a instala")
    en.add_argument("tool", choices=TOOLS)
    dis = sub.add_parser("disable", help="desliga uma ferramenta (reversível)")
    dis.add_argument("tool", choices=TOOLS)

    mode = sub.add_parser("set-mode", help="intensidade padrão do ponytail ou do caveman")
    mode.add_argument("tool", choices=("ponytail", "caveman"))
    mode.add_argument("mode", choices=MODES)

    proxy = sub.add_parser("proxy", help="gerencia o proxy local do headroom")
    proxy.add_argument("action", choices=("ensure", "start", "stop", "status"))

    sub.add_parser("session-hook", help="uso interno: hook SessionStart do Claude Code")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    paths = Paths.from_env()
    config = load_config(paths)
    if args.command == "status":
        return cmd_status(args, paths, config)
    if args.command == "doctor":
        return cmd_doctor(args, paths, config)
    if args.command == "install":
        return cmd_install(args, paths, config)
    if args.command == "enable":
        return cmd_enable(args, paths, config, True)
    if args.command == "disable":
        return cmd_enable(args, paths, config, False)
    if args.command == "set-mode":
        return cmd_set_mode(args, paths, config)
    if args.command == "proxy":
        return cmd_proxy(args, paths, config)
    if args.command == "session-hook":
        return cmd_session_hook(args, paths, config)
    return 2


if __name__ == "__main__":
    sys.exit(main())

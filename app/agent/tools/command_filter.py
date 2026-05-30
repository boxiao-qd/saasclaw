"""Command filter — whitelist + blacklist terminal command filtering for SaaS mode.
Handles command chaining (&&, ||, ;), subshells ($()), and newline separators."""

import json
import re
import shlex
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "command_filter.yaml"
_config_cache: dict | None = None

# Shell metacharacters that chain multiple commands
_CHAIN_SEPARATORS = re.compile(r'&&|\|\||;|\n|\r|\$\(|\`')

# Redirect patterns including curl -o and wget -O
_REDIRECT_RE = re.compile(r'(?:>>|>|(?:(?:curl|wget)\s+.*-(?:o|O)\s+\S+))')


def _load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
    else:
        _config_cache = {
            "whitelist": [],
            "blacklist_patterns": [],
            "dangerous_flags": ["-i", "--in-place", "-w", "--write", "-c", "-o", "-O"],
            "redirect_patterns": [">", ">>"],
        }
    return _config_cache


def _split_chained_commands(command: str) -> list[str]:
    """Split a shell command string by chain separators (&&, ||, ;, \\n, \\r).
    Also detect subshell invocations ($() and backticks) as separate commands."""
    parts = _CHAIN_SEPARATORS.split(command)
    return [p.strip() for p in parts if p.strip()]


def _extract_base_command(command_segment: str) -> str:
    """Extract the base command (first token) from a single command segment."""
    try:
        tokens = shlex.split(command_segment)
        return tokens[0] if tokens else ""
    except ValueError:
        parts = command_segment.strip().split()
        return parts[0] if parts else ""


def _has_redirect(command: str) -> bool:
    """Check if command contains output redirect to file (>, >>, curl -o, wget -O)."""
    # Check shell redirects > and >>
    stripped = command.strip()
    # Match > or >> not inside quotes, not part of comparison operators
    if re.search(r'[^\-=]\s*>[^>=]', stripped) or stripped.startswith('>'):
        return True
    if '>>' in stripped:
        return True
    # Check curl -o and wget -O (file output flags)
    if re.search(r'\bcurl\b.*-o\b', stripped) or re.search(r'\bwget\b.*-O\b', stripped):
        return True
    return False


def _has_dangerous_flag(command_segment: str) -> str | None:
    """Check if command segment contains dangerous flags. Returns the flag found."""
    config = _load_config()
    base_cmd = _extract_base_command(command_segment)
    # Only check dangerous flags for commands where they're relevant
    for flag in config.get("dangerous_flags", []):
        # For -i: only relevant for sed (sed -i modifies files in-place)
        if flag == "-i" and base_cmd == "sed":
            if f" {flag}" in command_segment or command_segment.startswith(f"sed{flag}"):
                return flag
        # For -c: relevant for python3 (python3 -c executes arbitrary code)
        if flag == "-c" and base_cmd in ("python3", "python"):
            return flag
        # For -o/-O: relevant for curl/wget (write to file)
        if flag in ("-o", "-O") and base_cmd in ("curl", "wget"):
            return flag
        # Generic dangerous flags (--in-place, -w, --write)
        if flag in ("--in-place", "-w", "--write") and flag in command_segment:
            return flag
    return None


def _has_subshell(command: str) -> bool:
    """Check if command contains subshell invocations ($() or backticks)."""
    return bool(re.search(r'\$\(|\`', command))


def _has_pipe_to_file_op(command: str) -> bool:
    """Check if command pipes to a file-writing operation (| tee, | cat >, etc).
    Uses proper pipe detection that doesn't confuse || with |."""
    config = _load_config()
    blacklist = set(config.get("blacklist_patterns", []))
    # Split on single | (not ||) — match pipe operator only
    # Replace || with placeholder first to avoid splitting on logical OR
    temp = command.replace('||', '  LOGIC_OR  ')
    if '|' in temp:
        pipe_parts = temp.split('|')
        for part in pipe_parts[1:]:
            part_cmd = _extract_base_command(part.strip().replace('LOGIC_OR', '||'))
            if part_cmd in blacklist:
                return True
    return False


def _has_exec_flag(command: str) -> bool:
    """Check if find command uses -exec flag (allows arbitrary command execution)."""
    base_cmd = _extract_base_command(command)
    if base_cmd == "find" and "-exec" in command:
        return True
    return False


def filter_command(command: str) -> dict:
    """Filter a terminal command for SaaS mode. Returns {allowed, reason} dict.

    Handles command chaining by splitting on &&, ||, ;, \\n, \\r and
    checking EACH sub-command individually against whitelist/blacklist.
    Also detects subshell invocations ($() and backticks) and rejects them.
    """
    if not command.strip():
        return {"allowed": False, "reason": "Empty command"}

    config = _load_config()
    whitelist = set(config.get("whitelist", []))
    blacklist = set(config.get("blacklist_patterns", []))

    # 0. Reject subshell invocations entirely ($() and backticks)
    if _has_subshell(command):
        return {"allowed": False, "reason": "Subshell invocations ($() / backticks) are blocked in SaaS mode"}

    # 0. Reject find -exec (arbitrary command execution)
    if _has_exec_flag(command):
        return {"allowed": False, "reason": "find -exec is blocked in SaaS mode (allows arbitrary command execution)"}

    # Split chained commands and check each individually
    sub_commands = _split_chained_commands(command)

    for sub_cmd in sub_commands:
        base_cmd = _extract_base_command(sub_cmd)

        # 1. Blacklist check (absolute reject)
        if base_cmd in blacklist:
            return {"allowed": False, "reason": f"Command '{base_cmd}' is blocked in SaaS mode (file operation)"}

        # 2. Redirect check (>, >>, curl -o, wget -O)
        if _has_redirect(sub_cmd):
            return {"allowed": False, "reason": "Output redirect to file (> / >> / curl -o / wget -O) is blocked in SaaS mode"}

        # 3. Pipe to file operation check
        if _has_pipe_to_file_op(sub_cmd):
            return {"allowed": False, "reason": "Piping to file-writing command is blocked in SaaS mode"}

        # 4. Dangerous flags check
        dangerous = _has_dangerous_flag(sub_cmd)
        if dangerous:
            return {"allowed": False, "reason": f"Command '{base_cmd}' with flag '{dangerous}' is blocked in SaaS mode"}

        # 5. Whitelist check
        if base_cmd in whitelist:
            continue  # This sub-command is allowed, check next

        # 6. Not in whitelist — reject (default deny)
        return {"allowed": False, "reason": f"Command '{base_cmd}' is not in the SaaS whitelist and is blocked by default"}

    # All sub-commands passed checks
    return {"allowed": True, "reason": ""}
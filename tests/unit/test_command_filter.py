"""Tests for command_filter.py — SaaS terminal command whitelist/blacklist filtering."""

import pytest
from app.agent.tools.command_filter import (
    filter_command,
    _split_chained_commands,
    _extract_base_command,
    _has_redirect,
    _has_dangerous_flag,
    _has_subshell,
    _has_pipe_to_file_op,
    _has_exec_flag,
)


class TestSplitChainedCommands:
    def test_single_command(self):
        assert _split_chained_commands("ls -la") == ["ls -la"]

    def test_and_chain(self):
        assert _split_chained_commands("ls && pwd") == ["ls", "pwd"]

    def test_or_chain(self):
        assert _split_chained_commands("ls || pwd") == ["ls", "pwd"]

    def test_semicolon_chain(self):
        assert _split_chained_commands("ls; pwd; date") == ["ls", "pwd", "date"]

    def test_newline_chain(self):
        assert _split_chained_commands("ls\npwd") == ["ls", "pwd"]

    def test_mixed_chain(self):
        parts = _split_chained_commands("ls && pwd || echo ok")
        assert parts == ["ls", "pwd", "echo ok"]

    def test_subshell_rejected_by_split(self):
        # $() is a chain separator, but _has_subshell catches it first
        parts = _split_chained_commands("echo $(whoami)")
        assert len(parts) >= 2  # splits around $()


class TestExtractBaseCommand:
    def test_simple(self):
        assert _extract_base_command("ls -la /tmp") == "ls"

    def test_no_args(self):
        assert _extract_base_command("pwd") == "pwd"

    def test_quoted_args(self):
        assert _extract_base_command("echo 'hello world'") == "echo"

    def test_empty(self):
        assert _extract_base_command("") == ""


class TestHasRedirect:
    def test_redirect_out(self):
        assert _has_redirect("echo hi > file.txt")

    def test_redirect_append(self):
        assert _has_redirect("echo hi >> file.txt")

    def test_curl_o(self):
        assert _has_redirect("curl http://x.com/api -o output.json")

    def test_wget_O(self):
        assert _has_redirect("wget http://x.com/file -O /tmp/file")

    def test_no_redirect(self):
        assert not _has_redirect("ls -la")

    def test_comparison_not_redirect(self):
        # "x >= 5" or "x => 5" should not be treated as redirect
        assert not _has_redirect("echo x >= 5")


class TestHasDangerousFlag:
    def test_sed_in_place(self):
        assert _has_dangerous_flag("sed -i 's/old/new/g' file.txt") == "-i"

    def test_python3_c(self):
        assert _has_dangerous_flag("python3 -c 'import os; os.system(\"rm -rf /\")'") == "-c"

    def test_curl_o_flag(self):
        assert _has_dangerous_flag("curl http://x.com -o out.txt") == "-o"

    def test_wget_O_flag(self):
        # -O is detected as dangerous (returns -o or -O depending on iteration order)
        result = _has_dangerous_flag("wget http://x.com -O out.txt")
        assert result in ("-o", "-O")

    def test_safe_command_no_flag(self):
        assert _has_dangerous_flag("ls -la") is None


class TestHasSubshell:
    def test_dollar_paren(self):
        assert _has_subshell("echo $(whoami)")

    def test_backtick(self):
        assert _has_subshell("echo `whoami`")

    def test_no_subshell(self):
        assert not _has_subshell("ls -la")


class TestHasPipeToFileOp:
    def test_pipe_to_tee(self):
        # tee is in blacklist_patterns
        assert _has_pipe_to_file_op("ls | tee output.txt")

    def test_pipe_to_cat_redirect(self):
        # cat is in blacklist_patterns
        assert _has_pipe_to_file_op("echo hi | cat > file.txt")

    def test_pipe_not_to_file(self):
        # grep is not in blacklist_patterns
        assert not _has_pipe_to_file_op("ls | grep foo")

    def test_logical_or_not_pipe(self):
        # || should not be treated as pipe
        assert not _has_pipe_to_file_op("ls || echo fail")


class TestHasExecFlag:
    def test_find_exec(self):
        assert _has_exec_flag("find /tmp -name '*.log' -exec rm {} \\;")

    def test_find_no_exec(self):
        assert not _has_exec_flag("find /tmp -name '*.log'")

    def test_not_find_command(self):
        assert not _has_exec_flag("ls -la")


class TestFilterCommand:
    """Full command filter integration tests."""

    def test_allowed_whitelist_command(self):
        result = filter_command("ls -la")
        assert result["allowed"] is True

    def test_allowed_echo(self):
        result = filter_command("echo hello")
        assert result["allowed"] is True

    def test_blocked_blacklist_command(self):
        result = filter_command("rm -rf /tmp")
        assert result["allowed"] is False
        assert "blocked" in result["reason"]

    def test_blocked_not_in_whitelist(self):
        result = filter_command("docker run image")
        assert result["allowed"] is False
        assert "not in the SaaS whitelist" in result["reason"]

    def test_blocked_subshell(self):
        result = filter_command("echo $(whoami)")
        assert result["allowed"] is False
        assert "Subshell" in result["reason"]

    def test_blocked_backtick(self):
        result = filter_command("echo `whoami`")
        assert result["allowed"] is False
        assert "Subshell" in result["reason"]

    def test_blocked_redirect(self):
        result = filter_command("echo hi > file.txt")
        assert result["allowed"] is False
        assert "redirect" in result["reason"].lower()

    def test_blocked_curl_o(self):
        result = filter_command("curl http://example.com/api -o data.json")
        assert result["allowed"] is False

    def test_blocked_wget_O(self):
        result = filter_command("wget http://example.com/file -O /tmp/file")
        assert result["allowed"] is False

    def test_blocked_python3_c(self):
        result = filter_command("python3 -c 'import os'")
        assert result["allowed"] is False
        assert "-c" in result["reason"]

    def test_blocked_find_exec(self):
        result = filter_command("find /tmp -name '*.log' -exec rm {} \\;")
        assert result["allowed"] is False
        assert "find -exec" in result["reason"]

    def test_blocked_chain_with_dangerous(self):
        # ls is safe, but rm in chain is not
        result = filter_command("ls && rm -rf /")
        assert result["allowed"] is False

    def test_blocked_chain_with_redirect(self):
        result = filter_command("ls && echo hi > file.txt")
        assert result["allowed"] is False
        assert "redirect" in result["reason"].lower()

    def test_allowed_chain_all_safe(self):
        result = filter_command("ls && pwd && date")
        assert result["allowed"] is True

    def test_blocked_pipe_to_blacklist(self):
        result = filter_command("ls | tee output.txt")
        assert result["allowed"] is False
        assert "Piping" in result["reason"]

    def test_blocked_sed_in_place(self):
        result = filter_command("sed -i 's/old/new/g' file.txt")
        assert result["allowed"] is False
        assert "-i" in result["reason"]

    def test_blocked_python3_not_in_whitelist(self):
        # python3 is removed from whitelist, blocked by default deny
        result = filter_command("python3 script.py")
        assert result["allowed"] is False
        # Either "not in the SaaS whitelist" or dangerous flag if -c is present
        assert "blocked" in result["reason"].lower()

    def test_blocked_curl_not_in_whitelist(self):
        # curl is removed from whitelist, blocked regardless
        result = filter_command("curl http://example.com/api")
        assert result["allowed"] is False
        assert "blocked" in result["reason"].lower()

    def test_blocked_pip_not_in_whitelist(self):
        result = filter_command("pip install package")
        assert result["allowed"] is False

    def test_blocked_awk_not_in_whitelist(self):
        result = filter_command("awk '{print $1}' file.txt")
        assert result["allowed"] is False

    def test_blocked_env_not_in_whitelist(self):
        result = filter_command("env")
        assert result["allowed"] is False

    def test_empty_command_blocked(self):
        result = filter_command("")
        assert result["allowed"] is False

    def test_whitespace_only_blocked(self):
        result = filter_command("   ")
        assert result["allowed"] is False
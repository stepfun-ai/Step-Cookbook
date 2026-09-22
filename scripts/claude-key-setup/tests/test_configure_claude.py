"""Check both language releases using temporary configs and fake credentials."""

import errno
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import time
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
MODEL_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)


class ConfigureClaudeChecks:
    """Shared regressions; only the locale subclasses are collected as tests."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="claude-config-test-")
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "settings with spaces.json"

    def run_script(self, original, choice="1", model="", api_key="sk-test-only", env=None,
                   config_arg=None):
        if original is not None:
            self.config.write_bytes(original)
        self.key_echo_disabled = False
        pid, terminal = pty.fork()
        if pid == 0:
            os.chdir(self.directory.name)
            # Challenge the script with a normal, non-private inherited umask.
            os.umask(0o022)
            os.execvpe("bash", ["bash", str(self.script), "-c",
                                str(self.config) if config_arg is None else config_arg],
                       os.environ if env is None else env)
        output = bytearray()
        status = None
        stage = "choice"
        key_prompt_time = None
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if select.select([terminal], [], [], 0.05)[0]:
                    try:
                        data = os.read(terminal, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        data = b""
                    output.extend(data)
                if stage == "choice" and self.choice_prompt.encode() in output:
                    os.write(terminal, f"{choice}\n".encode())
                    stage = "key"
                elif stage == "key" and self.key_prompt.encode() in output:
                    if key_prompt_time is None:
                        key_prompt_time = time.monotonic()
                    # A prompt can arrive before read -s changes terminal flags.
                    # Wait for ECHO to be disabled before sending a fake secret.
                    self.key_echo_disabled = not bool(
                        termios.tcgetattr(terminal)[3] & termios.ECHO)
                    if self.key_echo_disabled or time.monotonic() - key_prompt_time >= 0.2:
                        os.write(terminal, f"{api_key}\n".encode())
                        stage = "model"
                elif stage == "model" and self.model_prompt.encode() in output:
                    os.write(terminal, f"{model}\n".encode())
                    stage = "done"
                child, status_value = os.waitpid(pid, os.WNOHANG)
                if child:
                    status = status_value
                    # Include output written immediately before process exit.
                    while select.select([terminal], [], [], 0)[0]:
                        try:
                            data = os.read(terminal, 65536)
                        except OSError as exc:
                            if exc.errno != errno.EIO:
                                raise
                            break
                        if not data:
                            break
                        output.extend(data)
                    break
            if status is None:
                self.fail("Script timed out: " + output.decode(errors="replace"))
        finally:
            os.close(terminal)
            if status is None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status), output.decode(errors="replace")

    def assert_backup_and_cleanup(self, original):
        backups = list(self.config.parent.glob(self.config.name + ".bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.config.parent.glob(self.config.name + ".tmp.*")), [])

    def assert_explicit_path_selected(self, config_arg=None):
        # Check the resolver before a missing/non-regular path is run end to end.
        # This prevents a regressed fallback from touching the user's real config.
        functions = self.script_functions()
        requested_path = str(self.config) if config_arg is None else config_arg
        result = subprocess.run(
            ["bash", "-c", functions + '\nCLAUDE_CONFIG="$1"\nfind_config_file',
             "test", requested_path], cwd=self.directory.name,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), requested_path)

    def script_functions(self):
        source = self.script.read_text(encoding="utf-8")
        anchor = "# === MAIN ==="
        # Refuse to evaluate a whole script if its extraction marker changes.
        self.assertEqual(source.count(anchor), 1, "Expected one main-program marker")
        return source.split(anchor)[0]

    def assert_env(self, config, endpoint, model, api_key="sk-test-only"):
        expected = {key: model for key in MODEL_KEYS}
        expected.update(ANTHROPIC_BASE_URL=endpoint, ANTHROPIC_AUTH_TOKEN=api_key)
        self.assertEqual(config["env"], expected)

    def test_preserves_every_non_env_setting(self):
        settings = {
            "env": {"ANTHROPIC_MODEL": "old-model", "OLD_VARIABLE": "remove-me"},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": 'echo "保留 hook"'}
            ]}]},
            "theme": "dark",
            "model": "keep-existing-model",
            "statusLine": {"type": "command", "command": "echo status"},
            "permissions": {"allow": ["Bash(git status:*)"], "deny": []},
            "enabledPlugins": {"example@marketplace": True},
            "extraKnownMarketplaces": {"example": {"source": {"source": "github", "repo": "a/b"}}},
            "custom": {"empty": {}, "null": None, "false": False, "count": 3},
        }
        original = json.dumps(settings, ensure_ascii=False).encode()
        code, output = self.run_script(original)
        self.assertEqual(code, 0, output)
        actual = json.loads(self.config.read_bytes())
        self.assertEqual({k: v for k, v in actual.items() if k != "env"},
                         {k: v for k, v in settings.items() if k != "env"})
        self.assert_env(actual, self.official_endpoint, "step-5-preview")
        self.assert_backup_and_cleanup(original)

    def test_step_plan_uses_new_default(self):
        original = b'{"theme":"light"}'
        code, output = self.run_script(original, choice="2")
        self.assertEqual(code, 0, output)
        actual = json.loads(self.config.read_bytes())
        self.assertEqual(actual["theme"], "light")
        self.assert_env(actual, self.step_plan_endpoint, "step-5-preview")
        self.assert_backup_and_cleanup(original)

    def test_previous_model_remains_supported(self):
        code, output = self.run_script(b"{}", model="step-3.5-flash")
        self.assertEqual(code, 0, output)
        self.assert_env(json.loads(self.config.read_bytes()),
                        self.official_endpoint, "step-3.5-flash")

    def test_escapes_api_key_and_custom_model(self):
        api_key = 'sk-test-"quoted"\\path'
        model = 'custom-"model"\\name'
        code, output = self.run_script(b"{}", model=model, api_key=api_key)
        self.assertEqual(code, 0, output)
        self.assert_env(json.loads(self.config.read_bytes()),
                        self.official_endpoint, model, api_key)

    def test_key_input_and_summary_do_not_expose_credentials(self):
        api_key = "sk-private-test-only-no-real-credential"
        code, output = self.run_script(b"{}", api_key=api_key)
        self.assertEqual(code, 0, output)
        self.assertTrue(self.key_echo_disabled, "API Key input must disable terminal echo")
        self.assertNotIn(api_key, output)
        self.assertNotIn(api_key[:10], output)
        self.assert_env(json.loads(self.config.read_bytes()),
                        self.official_endpoint, "step-5-preview", api_key)

    def test_jq_process_arguments_and_environment_do_not_include_credentials(self):
        wrapper_directory = self.config.parent / "test-bin"
        wrapper_directory.mkdir()
        probe_log = self.config.parent / "jq-credential-probe.jsonl"
        wrapper = wrapper_directory / "jq"
        api_key = "sk-fake-argv-probe-only"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            f"fake_key = {api_key!r}\n"
            "probe = {\n"
            "    'version_probe': sys.argv[1:] == ['--version'],\n"
            "    'key_in_arguments': any(fake_key in value for value in sys.argv[1:]),\n"
            "    'environment_keys_with_input_key': [name for name, value in os.environ.items() if fake_key in value],\n"
            "}\n"
            "with open(os.environ['CLAUDE_TEST_JQ_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(probe) + '\\n')\n"
            "os.execv(os.environ['CLAUDE_TEST_REAL_JQ'], ['jq', *sys.argv[1:]])\n"
        )
        wrapper.chmod(0o700)
        environment = os.environ.copy()
        environment.update(
            PATH=str(wrapper_directory) + os.pathsep + environment.get("PATH", ""),
            CLAUDE_TEST_JQ_LOG=str(probe_log),
            CLAUDE_TEST_REAL_JQ=shutil.which("jq"),
            # Bash assignments preserve an inherited variable's export flag.
            # The newly entered key must not inherit this flag in the script.
            API_KEY="exported-placeholder",
        )
        code, output = self.run_script(b"{}", api_key=api_key, env=environment)
        self.assertEqual(code, 0, output)
        probes = [json.loads(line) for line in probe_log.read_text().splitlines()]
        self.assertGreaterEqual(len(probes), 2, "Expected version and config jq invocations")
        self.assertTrue(any(not probe["version_probe"] for probe in probes))
        for probe in probes:
            self.assertFalse(probe["key_in_arguments"], "Entered key leaked into jq arguments")
            self.assertEqual(probe["environment_keys_with_input_key"], [],
                             "Entered key leaked into jq environment")
        self.assert_env(json.loads(self.config.read_bytes()),
                        self.official_endpoint, "step-5-preview", api_key)

    def test_private_config_and_backup_from_previously_readable_config(self):
        original = b'{"theme":"dark","env":{"ANTHROPIC_AUTH_TOKEN":"old-fake-key"}}'
        self.config.write_bytes(original)
        self.config.chmod(0o644)
        code, output = self.run_script(None)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assert_backup_and_cleanup(original)

    def test_missing_explicit_config_creates_private_nested_path(self):
        self.config = self.config.parent / "new custom config" / "nested" / "settings.json"
        self.assert_explicit_path_selected()
        code, output = self.run_script(None)
        self.assertEqual(code, 0, output)
        self.assert_env(json.loads(self.config.read_bytes()),
                        self.official_endpoint, "step-5-preview")
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.config.parent.parent.stat().st_mode & 0o777, 0o700)
        backups = list(self.config.parent.glob(self.config.name + ".bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.config.parent.glob(self.config.name + ".tmp.*")), [])

    def test_bare_relative_config_path_creates_file_in_working_directory(self):
        self.assert_explicit_path_selected(config_arg=self.config.name)
        code, output = self.run_script(None, config_arg=self.config.name)
        self.assertEqual(code, 0, output)
        self.assert_env(json.loads(self.config.read_bytes()),
                        self.official_endpoint, "step-5-preview")
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        backups = list(self.config.parent.glob(self.config.name + ".bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_bytes()), {"env": {}})
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.config.parent.glob(self.config.name + ".tmp.*")), [])

    def test_backup_copy_failure_preserves_original_and_removes_partial_backup(self):
        wrapper_directory = self.config.parent / "test-bin"
        wrapper_directory.mkdir()
        wrapper = wrapper_directory / "cat"
        wrapper.write_text(
            "#!/bin/bash\n"
            "printf '%s' 'partial dummy backup content'\n"
            "printf '%s\\n' 'simulated backup-copy failure' >&2\n"
            "exit 73\n"
        )
        wrapper.chmod(0o700)
        environment = os.environ.copy()
        environment["PATH"] = str(wrapper_directory) + os.pathsep + environment.get("PATH", "")
        original = b'{"theme":"keep-dark","env":{"ANTHROPIC_AUTH_TOKEN":"old-fake-key"}}'
        code, output = self.run_script(original, env=environment)
        self.assertNotEqual(code, 0, output)
        self.assertIn("simulated backup-copy failure", output)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(list(self.config.parent.glob(self.config.name + ".bak.*")), [])
        self.assertEqual(list(self.config.parent.glob(self.config.name + ".tmp.*")), [])
        for success_message in self.success_messages:
            self.assertNotIn(success_message, output)

    def test_nonregular_explicit_paths_fail_without_fallback(self):
        root = self.config.parent
        for kind in ("directory", "fifo", "dangling-symlink"):
            with self.subTest(kind=kind):
                self.config = root / kind
                if kind == "directory":
                    self.config.mkdir()
                elif kind == "fifo":
                    os.mkfifo(self.config)
                else:
                    self.config.symlink_to("missing-target.json")
                self.assert_explicit_path_selected()
                before = self.config.lstat()
                code, output = self.run_script(None)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(self.config.lstat().st_ino, before.st_ino)
                self.assertEqual(self.config.lstat().st_mode, before.st_mode)
                self.assertEqual(list(root.glob(self.config.name + ".bak.*")), [])
                self.assertEqual(list(root.glob(self.config.name + ".tmp.*")), [])
                self.assertNotIn(self.key_prompt.rstrip(), output)

    def test_rejects_invalid_or_non_object_json_without_changing_original(self):
        for original in (b'{"hooks":', b"", b"[]", b"null", b'"text"', b"true", b"42", b"{}\n{}"):
            with self.subTest(original=original):
                for backup in self.config.parent.glob(self.config.name + ".bak.*"):
                    backup.unlink()
                code, output = self.run_script(original)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(self.config.read_bytes(), original)
                self.assert_backup_and_cleanup(original)

    def test_preserves_deep_nested_configuration(self):
        nested = {"command": "echo keep"}
        for _ in range(20):
            nested = {"nested": nested}
        original = json.dumps({"custom": nested}).encode()
        code, output = self.run_script(original)
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(self.config.read_bytes())["custom"], nested)

    def test_updates_symlink_target_without_replacing_the_link(self):
        target_directory = self.config.parent / "dotfiles"
        target_directory.mkdir()
        target = target_directory / "claude.json"
        self.config.symlink_to(Path("dotfiles") / "claude.json")
        original = b'{"theme":"dark","env":{"OLD_VARIABLE":"remove-me"}}'
        code, output = self.run_script(original)
        self.assertEqual(code, 0, output)
        self.assertTrue(self.config.is_symlink())
        actual = json.loads(target.read_bytes())
        self.assertEqual(actual["theme"], "dark")
        self.assert_env(actual, self.official_endpoint, "step-5-preview")
        self.assert_backup_and_cleanup(original)
        self.assertEqual(list(target_directory.glob("*.tmp.*")), [])

    def test_new_base_config_does_not_pin_a_top_level_model(self):
        functions = self.script_functions()
        result = subprocess.run(
            ["bash", "-c", functions + '\ncreate_base_config "$1"', "test", str(self.config)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.config.read_bytes()), {"env": {}})


@unittest.skipUnless(shutil.which("jq"), "Bash script requires jq")
class ChineseConfigureClaudeTests(ConfigureClaudeChecks, unittest.TestCase):
    official_endpoint = "https://api.stepfun.com"
    step_plan_endpoint = "https://api.stepfun.com/step_plan"
    script = REPOSITORY / "zh-CN" / "configure_claude.sh"
    choice_prompt = "请输入数字 [1-2]: "
    key_prompt = "请输入 StepFun API Key: "
    model_prompt = "模型名称 [默认: "
    success_messages = ("配置已更新", "配置完成")


@unittest.skipUnless(shutil.which("jq"), "Bash script requires jq")
class EnglishConfigureClaudeTests(ConfigureClaudeChecks, unittest.TestCase):
    official_endpoint = "https://api.stepfun.ai/"
    step_plan_endpoint = "https://api.stepfun.ai/step_plan"
    script = REPOSITORY / "en" / "configure_claude.sh"
    choice_prompt = "Enter a number [1-2]: "
    key_prompt = "Enter your StepFun API Key: "
    model_prompt = "Model name [default: "
    success_messages = ("Claude Code configuration updated", "Setup complete!")


class ReleaseIntegrityTests(unittest.TestCase):
    def test_legacy_entry_points_match_chinese_release(self):
        for name in ("configure_claude.sh", "configure_claude.ps1"):
            with self.subTest(name=name):
                self.assertEqual((REPOSITORY / name).read_bytes(),
                                 (REPOSITORY / "zh-CN" / name).read_bytes())

    def test_english_release_has_no_untranslated_chinese_text(self):
        chinese = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
        for name in ("configure_claude.sh", "configure_claude.ps1", "README.md"):
            with self.subTest(name=name):
                source = (REPOSITORY / "en" / name).read_text(encoding="utf-8-sig")
                self.assertIsNone(chinese.search(source), f"Untranslated Chinese text in en/{name}")


if __name__ == "__main__":
    unittest.main()

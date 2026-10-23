"""Windows branches are simulated on other systems; the .bat smoke runs on Windows."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from companion.host import read_message, write_message
from companion.system import configure_binary_stdio, downloads_directory, find_tool, quiet_process_options, reveal_command, tool_search_path
from scripts.install_companion import HOST, ROOT, register_windows_manifest, windows_registry_path, write_native_host


class WindowsInstallationTests(unittest.TestCase):
    def test_windows_manifest_uses_relative_batch_launcher_and_only_the_chosen_extension(self):
        with tempfile.TemporaryDirectory(prefix="Instant project ") as temporary:
            with patch("scripts.install_companion.register_windows_manifest") as register:
                manifest_path = write_native_host(Path(temporary), ROOT / ".venv/Scripts/python.exe", "b" * 32, platform="win32")
                register.assert_called_once_with(manifest_path, "chrome")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["allowed_origins"], ["chrome-extension://" + "b" * 32 + "/"])
            launcher = Path(manifest["path"])
            self.assertEqual(launcher.name, "native-host-windows.bat")
            script = launcher.read_text(encoding="ascii")
            self.assertIn('"%~dp0..\\.venv\\Scripts\\python.exe"', script)
            self.assertIn('"%~dp0host.py"', script)
            self.assertIn("DisableDelayedExpansion", script)
            self.assertNotIn(str(ROOT), script)

    def test_registry_binding_is_per_user_and_stored_in_chromes_32_bit_lookup_view(self):
        registry = MagicMock()
        registry.KEY_SET_VALUE = 2
        registry.KEY_WOW64_32KEY = 512
        with patch.dict(sys.modules, {"winreg": registry}):
            register_windows_manifest(Path("manifest.json"), "chrome")
        registry.CreateKeyEx.assert_called_once_with(
            registry.HKEY_CURRENT_USER,
            rf"Software\Google\Chrome\NativeMessagingHosts\{HOST}", 0, 514,
        )
        registry.SetValueEx.assert_called_once_with(
            registry.CreateKeyEx.return_value.__enter__.return_value,
            "", 0, registry.REG_SZ, "manifest.json",
        )
        self.assertEqual(windows_registry_path("chromium"), rf"Software\Chromium\NativeMessagingHosts\{HOST}")

    def test_test_mode_does_not_change_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch("scripts.install_companion.register_windows_manifest") as register:
                write_native_host(Path(temporary), ROOT / ".venv/Scripts/python.exe", "a" * 32, platform="win32", register=False)
                register.assert_not_called()


class WindowsRuntimeTests(unittest.TestCase):
    def test_native_stdin_and_stdout_are_set_to_binary(self):
        setmode = MagicMock()
        with patch.dict(sys.modules, {"msvcrt": SimpleNamespace(setmode=setmode)}), patch.object(os, "O_BINARY", 0x8000, create=True):
            configure_binary_stdio("win32", SimpleNamespace(fileno=lambda: 10), SimpleNamespace(fileno=lambda: 11))
        self.assertEqual(setmode.call_args_list, [unittest.mock.call(10, 0x8000), unittest.mock.call(11, 0x8000)])

    def test_winget_and_project_tools_are_discoverable_without_restarting_the_shell(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCALAPPDATA": temporary}):
            winget = Path(temporary) / "Microsoft/WinGet/Packages/Gyan.FFmpeg_test/ffmpeg-8-full_build/bin"
            winget.mkdir(parents=True)
            search = tool_search_path("win32")
            self.assertIn(str(winget), search)
            self.assertIn(str(Path(temporary) / "Microsoft/WinGet/Links"), search)
            self.assertIn(str(ROOT / "tools/ffmpeg/bin"), search)
            with patch("companion.system.shutil.which", return_value=str(winget / "ffmpeg.exe")) as which:
                self.assertTrue(find_tool("ffmpeg", "win32").endswith("ffmpeg.exe"))
                which.assert_called_once_with("ffmpeg.exe", path=search)

    def test_redirected_downloads_folder_is_respected(self):
        registry = MagicMock()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "My saved videos"
            registry.QueryValueEx.return_value = (str(destination), 1)
            with patch.dict(sys.modules, {"winreg": registry}):
                self.assertEqual(downloads_directory("win32"), destination)
            registry.QueryValueEx.assert_called_once_with(
                registry.OpenKey.return_value.__enter__.return_value,
                "{374DE290-123F-4565-9164-39C4925E467B}",
            )

    def test_explorer_receives_the_filename_as_a_separate_argument(self):
        filename = r"C:\Users\A B\Downloads\Reel & memories.mp4"
        command = reveal_command(filename, "win32")
        self.assertEqual(command[1:], ["/select,", filename])
        self.assertTrue(command[0].endswith("explorer.exe"))
        self.assertEqual(quiet_process_options("linux"), {})
        self.assertIn("creationflags", quiet_process_options("win32"))

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows cmd.exe; simulated Windows checks run on every OS")
    def test_real_windows_batch_host_preserves_binary_frames_and_unicode_from_another_directory(self):
        frames = io.BytesIO()
        messages = []
        for low_byte in (0x0A, 0x0D):
            for padding in range(300):
                message = {"id": f"windows-{low_byte}-فيديو", "action": "ping", "padding": "x" * padding}
                if len(json.dumps(message, ensure_ascii=False).encode("utf-8")) % 256 == low_byte:
                    messages.append(message)
                    write_message(frames, message)
                    break
        self.assertEqual(len(messages), 2)
        with tempfile.TemporaryDirectory(prefix="Instant unrelated cwd ") as temporary:
            process = subprocess.run([
                os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(ROOT / "companion/native-host-windows.bat"),
            ], input=frames.getvalue(), capture_output=True, timeout=30, cwd=temporary)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        output = io.BytesIO(process.stdout)
        for message in messages:
            reply = read_message(output)
            self.assertEqual(reply["id"], message["id"])
            self.assertEqual(reply["type"], "result")
            self.assertTrue(reply["data"]["ffmpeg"])
        self.assertIsNone(read_message(output))


if __name__ == "__main__":
    unittest.main()

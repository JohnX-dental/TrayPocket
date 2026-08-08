from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "traypocket.py"
SPEC = importlib.util.spec_from_file_location("traypocket_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
traypocket = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = traypocket
SPEC.loader.exec_module(traypocket)


class FakeProcess:
    def __init__(self, pid: int, alive: bool = True) -> None:
        self.pid = pid
        self.alive = alive

    def poll(self) -> int | None:
        return None if self.alive else 0


class FakeUser32:
    def __init__(self) -> None:
        self.valid: set[int] = set()
        self.visible: set[int] = set()
        self.show_calls: list[tuple[int, int]] = []
        self.focus_calls: list[int] = []

    def IsWindow(self, window: int) -> bool:
        return window in self.valid

    def IsWindowVisible(self, window: int) -> bool:
        return window in self.visible

    def ShowWindow(self, window: int, command: int) -> bool:
        self.show_calls.append((window, command))
        if command == traypocket.SW_HIDE:
            self.visible.discard(window)
        elif command in (traypocket.SW_SHOW, traypocket.SW_RESTORE):
            self.visible.add(window)
        return True

    def SetForegroundWindow(self, window: int) -> bool:
        self.focus_calls.append(window)
        return True

    def GetDesktopWindow(self) -> int:
        return -1

    def GetShellWindow(self) -> int:
        return -2

    def GetWindow(self, _window: int, _command: int) -> int:
        return 0

    def DestroyIcon(self, _icon: int) -> bool:
        return True

    def DefWindowProcW(self, _hwnd: int, _msg: int, _wparam: int, _lparam: int) -> int:
        return 0


class TrayStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_user32 = FakeUser32()
        self.app = traypocket.TrayPocketApp.__new__(traypocket.TrayPocketApp)
        self.app.items = []
        self.app.hwnd = -3
        self.app.main_icon = 999
        self.app.next_item_id = traypocket.ITEM_ICON_BASE_ID
        self.app.show_item_tray_icons = False
        self.app._add_item_tray_icon = mock.Mock()
        self.app._remove_tray_icon = mock.Mock()
        self.app.play_hide_sound = mock.Mock()
        self.app.show_balloon = mock.Mock()
        self.app.mark_items_changed = mock.Mock()

        self.user32_patch = mock.patch.object(traypocket, "user32", self.fake_user32)
        self.user32_patch.start()
        self.addCleanup(self.user32_patch.stop)

    def make_item(
        self,
        *,
        window: int = 100,
        process: FakeProcess | None = None,
        item_id: int = traypocket.ITEM_ICON_BASE_ID,
    ) -> traypocket.TrayedItem:
        item = traypocket.TrayedItem(
            item_id=item_id,
            window=window,
            process=process,
            executable_path=r"C:\Apps\Example\example.exe",
            title="Example",
            started_by_traypocket=process is not None,
            hicon=123,
        )
        item.process_id = process.pid if process else 42
        return item

    def test_monitor_rehides_a_managed_window_that_becomes_visible(self) -> None:
        item = self.make_item()
        self.app.items.append(item)
        self.fake_user32.valid.add(item.window)
        self.fake_user32.visible.add(item.window)

        self.app.monitor_items()

        self.assertIn((item.window, traypocket.SW_HIDE), self.fake_user32.show_calls)
        self.assertEqual([item], self.app.items)

    def test_recreated_window_reuses_existing_item_instead_of_adding_duplicate(self) -> None:
        process = FakeProcess(42)
        old_item = self.make_item(window=100, process=process)
        self.app.items.append(old_item)
        self.fake_user32.valid.add(200)
        self.fake_user32.visible.add(200)

        with (
            mock.patch.object(traypocket, "get_window_process_id", return_value=42),
            mock.patch.object(traypocket, "get_class_name", return_value="ExampleWindow"),
            mock.patch.object(traypocket, "get_window_title", return_value="Example refreshed"),
            mock.patch.object(traypocket, "extract_icon", return_value=321),
        ):
            self.app.add_window_to_tray(200, process, old_item.executable_path, True)

        self.assertEqual(1, len(self.app.items))
        self.assertIs(old_item, self.app.items[0])
        self.assertEqual(200, old_item.window)
        self.assertIn((200, traypocket.SW_HIDE), self.fake_user32.show_calls)

    def test_restore_via_replacement_window_disposes_the_managed_item(self) -> None:
        process = FakeProcess(42)
        item = self.make_item(window=0, process=process)
        self.app.items.append(item)
        self.fake_user32.valid.add(200)

        with mock.patch.object(traypocket, "find_main_window_for_pid", return_value=200):
            self.app.restore_or_focus_item(item)

        self.assertNotIn(item, self.app.items)
        self.app._remove_tray_icon.assert_called_once_with(item.item_id)

    def test_collection_mode_does_not_add_one_system_tray_icon_per_item(self) -> None:
        self.fake_user32.valid.add(200)
        self.fake_user32.visible.add(200)

        with (
            mock.patch.object(traypocket, "get_window_process_id", return_value=42),
            mock.patch.object(traypocket, "get_class_name", return_value="ExampleWindow"),
            mock.patch.object(traypocket, "get_window_title", return_value="Example"),
            mock.patch.object(traypocket, "extract_icon", return_value=321),
        ):
            self.app.add_window_to_tray(200, None, r"C:\Apps\Example\example.exe", False)

        self.assertEqual(1, len(self.app.items))
        self.app._add_item_tray_icon.assert_not_called()

    def test_main_icon_double_click_opens_collection_panel(self) -> None:
        self.app.show_collection_panel = mock.Mock()

        self.app._wndproc(
            self.app.hwnd,
            traypocket.WM_TRAYICON,
            traypocket.MAIN_ICON_ID,
            traypocket.WM_LBUTTONDBLCLK,
        )

        self.app.show_collection_panel.assert_called_once_with()


    def test_stale_mutex_without_window_does_not_block_startup(self) -> None:
        fake_kernel = mock.Mock()
        fake_kernel.CreateMutexW.return_value = 123
        fake_kernel.GetLastError.return_value = traypocket.ERROR_ALREADY_EXISTS
        fake_user = mock.Mock()
        fake_user.FindWindowW.return_value = 0
        app = mock.Mock()

        with (
            mock.patch.object(traypocket, "kernel32", fake_kernel),
            mock.patch.object(traypocket, "user32", fake_user),
            mock.patch.object(traypocket, "TrayPocketApp", return_value=app),
        ):
            self.assertEqual(0, traypocket.main([]))

        fake_user.MessageBoxW.assert_not_called()
        app.run.assert_called_once_with()
        fake_kernel.CloseHandle.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()

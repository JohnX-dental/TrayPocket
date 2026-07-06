#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TrayPocket Python edition.

Pure-stdlib Windows tray utility for hiding normal desktop windows into the
system tray. It intentionally avoids third-party packages so users can inspect
and run the code directly with Python on Windows.
"""

from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import winsound
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog


APP_NAME = "TrayPocket"
WINDOW_CLASS = "TrayPocketPythonHiddenWindow"
MUTEX_NAME = "TrayPocket.Python.SingleInstance.Mutex"
CONFIG_FILE_NAME = "apps.txt"
SETTINGS_FILE_NAME = "settings.txt"
PLAY_SOUND_ON_HIDE_KEY = "PlaySoundOnHide"
MENU_LANGUAGE_KEY = "MenuLanguage"
CHINESE_MENU_LANGUAGE = "zh-CN"
RECENT_APP_LIMIT = 20

WM_USER = 0x0400
WM_APP = 0x8000
WM_TRAYICON = WM_USER + 1
WM_PROCESS_READY = WM_APP + 1
WM_COPYDATA = 0x004A
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_HOTKEY = 0x0312
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

MF_STRING = 0x00000000
MF_GRAYED = 0x00000001
MF_CHECKED = 0x00000008
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
GW_OWNER = 4

MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
VK_Z = 0x5A
HOTKEY_ID = 0x5450

ERROR_ALREADY_EXISTS = 183
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

MAIN_ICON_ID = 1
ITEM_ICON_BASE_ID = 100


user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
ENUMWINDOWSPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [
        ("dwData", ctypes.c_size_t),
        ("cbData", wintypes.DWORD),
        ("lpData", ctypes.c_void_p),
    ]


user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPVOID,
]
user32.TrackPopupMenu.restype = wintypes.UINT
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetDesktopWindow.restype = wintypes.HWND
user32.GetShellWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.EnumWindows.argtypes = [ENUMWINDOWSPROC, wintypes.LPARAM]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]

shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.ExtractIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
shell32.ExtractIconW.restype = wintypes.HICON

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


@dataclass
class TrayedItem:
    item_id: int
    window: int
    process: subprocess.Popen | None
    executable_path: str
    title: str
    started_by_traypocket: bool
    hicon: int


class TrayPocketApp:
    def __init__(self, startup_args: list[str]) -> None:
        self.startup_args = startup_args
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.hwnd = None
        self.wndproc_ref = WNDPROC(self._wndproc)
        self.main_icon = user32.LoadIconW(None, ctypes.c_wchar_p(32512))
        self.items: list[TrayedItem] = []
        self.recent_apps: list[str] = []
        self.pending_results: dict[int, tuple[subprocess.Popen | None, str, int]] = {}
        self.pending_queue: queue.Queue[tuple[subprocess.Popen | None, str, int]] = queue.Queue()
        self.next_pending_id = 1
        self.next_item_id = ITEM_ICON_BASE_ID
        self.menu_actions: dict[int, callable] = {}
        self.next_command_id = 1000
        self.config_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
        self.config_file = self.config_dir / CONFIG_FILE_NAME
        self.settings_file = self.config_dir / SETTINGS_FILE_NAME
        self.play_sound_on_hide = False
        self.menu_language = CHINESE_MENU_LANGUAGE
        self.disposed = False

        self.load_recent_apps()
        self.load_settings()
        self._create_hidden_window()
        self._add_main_tray_icon()
        self._register_hotkey()

    def run(self) -> None:
        for path in self.startup_args:
            if path.strip():
                self.start_program_to_tray(path)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _create_hidden_window(self) -> None:
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self.wndproc_ref
        wc.hInstance = self.hinstance
        wc.hIcon = self.main_icon
        wc.hIconSm = self.main_icon
        wc.lpszClassName = WINDOW_CLASS
        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom and ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            raise ctypes.WinError(ctypes.get_last_error())

        self.hwnd = user32.CreateWindowExW(
            0,
            WINDOW_CLASS,
            APP_NAME,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            self.hinstance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

    def _register_hotkey(self) -> None:
        ok = user32.RegisterHotKey(self.hwnd, HOTKEY_ID, MOD_WIN | MOD_SHIFT | MOD_NOREPEAT, VK_Z)
        if not ok:
            self.show_balloon("Win+Shift+Z 已被占用。托盘菜单仍可正常使用。")

    def _base_notify_data(self, icon_id: int) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = icon_id
        return nid

    def _add_main_tray_icon(self) -> None:
        nid = self._base_notify_data(MAIN_ICON_ID)
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.main_icon
        nid.szTip = APP_NAME
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _add_item_tray_icon(self, item: TrayedItem) -> None:
        nid = self._base_notify_data(item.item_id)
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = item.hicon
        nid.szTip = short_tray_text(item.title)
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _remove_tray_icon(self, icon_id: int) -> None:
        nid = self._base_notify_data(icon_id)
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_TRAYICON:
            icon_id = int(wparam)
            event = int(lparam)
            if event == WM_RBUTTONUP:
                self.show_menu_for_icon(icon_id)
                return 0
            if event == WM_LBUTTONDBLCLK:
                if icon_id == MAIN_ICON_ID:
                    self.select_and_start_program()
                else:
                    item = self.find_item_by_id(icon_id)
                    if item:
                        self.restore_or_focus_item(item)
                return 0

        if msg == WM_HOTKEY and int(wparam) == HOTKEY_ID:
            self.hide_foreground_window_to_tray()
            return 0

        if msg == WM_PROCESS_READY:
            self._handle_process_ready(int(wparam))
            return 0

        if msg == WM_COPYDATA:
            self._handle_copy_data(lparam)
            return 1

        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def show_menu_for_icon(self, icon_id: int) -> None:
        if icon_id == MAIN_ICON_ID:
            self.show_main_menu()
            return

        item = self.find_item_by_id(icon_id)
        if item:
            self.show_item_menu(item)

    def show_main_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        self.menu_actions = {}
        self.next_command_id = 1000

        self._append_action(menu, "选择程序并托盘运行...", self.select_and_start_program)
        recent_menu = user32.CreatePopupMenu()
        if not self.recent_apps:
            self._append_text(recent_menu, "没有最近程序", disabled=True)
        else:
            for app_path in self.recent_apps:
                self._append_action(
                    recent_menu,
                    Path(app_path).stem or app_path,
                    lambda path=app_path: self.start_program_to_tray(path),
                )
        self._append_submenu(menu, "最近程序一键托盘运行", recent_menu)
        self._append_separator(menu)
        self._append_action(menu, "隐藏当前窗口到托盘 (Win+Shift+Z)", self.hide_foreground_window_to_tray)
        self._append_action(
            menu,
            f"恢复全部隐藏窗口 ({self.hidden_window_count()})",
            self.restore_all_hidden_windows,
            disabled=self.hidden_window_count() == 0,
        )

        if self.items:
            managed_menu = user32.CreatePopupMenu()
            for item in list(self.items):
                self._append_action(managed_menu, item.title, lambda trayed=item: self.restore_or_focus_item(trayed))
            self._append_submenu(menu, "当前托管项目", managed_menu)

        self._append_separator(menu)
        settings_menu = user32.CreatePopupMenu()
        self._append_action(settings_menu, "开机自动启动 TrayPocket", self.toggle_startup, checked=is_startup_enabled())
        self._append_action(settings_menu, "隐藏程序时播放提示音", self.toggle_hide_sound, checked=self.play_sound_on_hide)
        language_menu = user32.CreatePopupMenu()
        self._append_action(language_menu, "中文（简体）", self.use_chinese_menu, checked=self.is_chinese_menu())
        self._append_submenu(settings_menu, "菜单语言", language_menu)
        self._append_action(settings_menu, "打开配置文件夹", self.open_config_folder)
        self._append_submenu(menu, "设置", settings_menu)

        self._append_action(menu, "清空最近程序", self.clear_recent_apps, disabled=not self.recent_apps)
        self._append_separator(menu)
        self._append_action(menu, "退出并恢复隐藏窗口", self.exit)

        self._track_and_dispatch_menu(menu)
        user32.DestroyMenu(menu)

    def show_item_menu(self, item: TrayedItem) -> None:
        menu = user32.CreatePopupMenu()
        self.menu_actions = {}
        self.next_command_id = 2000

        self._append_action(menu, "查找窗口 / 聚焦" if not item.window else "恢复窗口", lambda: self.restore_or_focus_item(item))
        self._append_action(
            menu,
            "打开文件所在位置",
            lambda: open_file_location(item.executable_path),
            disabled=not Path(item.executable_path).exists(),
        )
        if not item.window:
            self._append_action(menu, "结束进程", lambda: self.stop_process_item(item))
            self._append_action(menu, "移除托盘图标", lambda: self.dispose_item(item))

        self._track_and_dispatch_menu(menu)
        user32.DestroyMenu(menu)

    def _append_text(self, menu: int, text: str, disabled: bool = False) -> None:
        flags = MF_STRING | (MF_GRAYED if disabled else 0)
        user32.AppendMenuW(menu, flags, 0, text)

    def _append_action(self, menu: int, text: str, action: callable, checked: bool = False, disabled: bool = False) -> None:
        command_id = self.next_command_id
        self.next_command_id += 1
        if not disabled:
            self.menu_actions[command_id] = action
        flags = MF_STRING
        if checked:
            flags |= MF_CHECKED
        if disabled:
            flags |= MF_GRAYED
        user32.AppendMenuW(menu, flags, command_id, text)

    def _append_submenu(self, menu: int, text: str, submenu: int) -> None:
        user32.AppendMenuW(menu, MF_STRING, submenu, text)

    def _append_separator(self, menu: int) -> None:
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

    def _track_and_dispatch_menu(self, menu: int) -> None:
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, self.hwnd, None)
        action = self.menu_actions.get(int(command))
        if action:
            action()

    def select_and_start_program(self) -> None:
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="选择要托盘运行的程序",
                filetypes=[("程序", "*.exe"), ("所有文件", "*.*")],
            )
            root.destroy()
            if path:
                self.start_program_to_tray(path)
        except Exception as exc:
            self.show_balloon(f"无法打开程序选择窗口：{exc}")

    def start_program_to_tray(self, path: str) -> None:
        executable_path = os.path.expandvars(path.strip().strip('"'))
        if not Path(executable_path).exists():
            self.show_balloon(f"找不到程序：{executable_path}")
            return

        self.add_recent_app(executable_path)
        try:
            process = subprocess.Popen([executable_path], cwd=str(Path(executable_path).parent))
        except Exception as exc:
            self.show_balloon(f"无法启动 {Path(executable_path).name}：{exc}")
            return

        token = self.next_pending_id
        self.next_pending_id += 1

        def wait_for_window() -> None:
            window = wait_for_main_window(process, 15.0)
            self.pending_results[token] = (process, executable_path, window)
            user32.PostMessageW(self.hwnd, WM_PROCESS_READY, token, 0)

        threading.Thread(target=wait_for_window, daemon=True).start()

    def _handle_process_ready(self, token: int) -> None:
        result = self.pending_results.pop(token, None)
        if not result or self.disposed:
            return
        process, executable_path, window = result
        if window and user32.IsWindow(window):
            self.add_window_to_tray(window, process, executable_path, True)
        else:
            self.add_background_process_to_tray(process, executable_path)

    def hide_foreground_window_to_tray(self) -> None:
        window = user32.GetForegroundWindow()
        if not self.can_hide_window(window):
            self.show_balloon("当前没有可隐藏的普通窗口。")
            return

        process_id = get_window_process_id(window)
        if process_id == os.getpid():
            return

        executable_path = executable_path_for_pid(process_id)
        self.add_window_to_tray(window, None, executable_path, False)

    def can_hide_window(self, window: int) -> bool:
        if not window:
            return False
        if window in (self.hwnd, user32.GetDesktopWindow(), user32.GetShellWindow()):
            return False
        if not user32.IsWindow(window) or not user32.IsWindowVisible(window):
            return False
        if user32.GetWindow(window, GW_OWNER):
            return False
        class_name = get_class_name(window)
        if class_name in {"Shell_TrayWnd", "WorkerW", "Progman", "Button"}:
            return False
        return self.find_item_by_window(window) is None

    def add_window_to_tray(
        self,
        window: int,
        process: subprocess.Popen | None,
        executable_path: str,
        started_by_traypocket: bool,
    ) -> None:
        if not self.can_hide_window(window):
            self.show_balloon("这个窗口不能隐藏到托盘。")
            return

        title = get_window_title(window) or filename_or_fallback(executable_path, "隐藏窗口")
        item = TrayedItem(
            item_id=self.next_item_id,
            window=window,
            process=process,
            executable_path=executable_path,
            title=title,
            started_by_traypocket=started_by_traypocket,
            hicon=extract_icon(executable_path),
        )
        self.next_item_id += 1
        self.items.append(item)
        self._add_item_tray_icon(item)
        user32.ShowWindow(window, SW_HIDE)
        self.play_hide_sound()
        self.show_balloon(f"已隐藏到托盘：{item.title}")

    def add_background_process_to_tray(self, process: subprocess.Popen, executable_path: str) -> None:
        item = TrayedItem(
            item_id=self.next_item_id,
            window=0,
            process=process,
            executable_path=executable_path,
            title=filename_or_fallback(executable_path, "后台进程"),
            started_by_traypocket=True,
            hicon=extract_icon(executable_path),
        )
        self.next_item_id += 1
        self.items.append(item)
        self._add_item_tray_icon(item)
        self.show_balloon(f"已作为后台进程托管：{item.title}")

    def restore_or_focus_item(self, item: TrayedItem) -> None:
        if item not in self.items:
            return
        if item.window and user32.IsWindow(item.window):
            user32.ShowWindow(item.window, SW_RESTORE)
            user32.ShowWindow(item.window, SW_SHOW)
            user32.SetForegroundWindow(item.window)
            self.dispose_item(item)
            return

        window = 0
        if item.process:
            window = find_main_window_for_pid(item.process.pid)
        if window:
            item.window = window
            user32.ShowWindow(window, SW_RESTORE)
            user32.ShowWindow(window, SW_SHOW)
            user32.SetForegroundWindow(window)
        else:
            self.show_balloon(f"没有找到可见窗口：{item.title}")

    def restore_all_hidden_windows(self) -> None:
        for item in list(self.items):
            if item.window and user32.IsWindow(item.window):
                user32.ShowWindow(item.window, SW_RESTORE)
                user32.ShowWindow(item.window, SW_SHOW)
                self.dispose_item(item)

    def stop_process_item(self, item: TrayedItem) -> None:
        if item.process is None:
            self.dispose_item(item)
            return
        try:
            if item.process.poll() is None:
                item.process.terminate()
                try:
                    item.process.wait(timeout=2.5)
                except subprocess.TimeoutExpired:
                    item.process.kill()
        except Exception as exc:
            self.show_balloon(f"无法结束 {item.title}：{exc}")
            return
        self.dispose_item(item)

    def dispose_item(self, item: TrayedItem) -> None:
        if item not in self.items:
            return
        self.items.remove(item)
        self._remove_tray_icon(item.item_id)
        if item.hicon and item.hicon != self.main_icon:
            user32.DestroyIcon(item.hicon)

    def find_item_by_id(self, item_id: int) -> TrayedItem | None:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def find_item_by_window(self, window: int) -> TrayedItem | None:
        for item in self.items:
            if item.window == window:
                return item
        return None

    def hidden_window_count(self) -> int:
        return sum(1 for item in self.items if item.window)

    def load_recent_apps(self) -> None:
        self.recent_apps.clear()
        try:
            if not self.config_file.exists():
                return
            for line in self.config_file.read_text(encoding="utf-8").splitlines():
                path = line.strip()
                if path and Path(path).exists():
                    self.recent_apps.append(path)
        except OSError:
            pass

    def save_recent_apps(self) -> None:
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text("\n".join(self.recent_apps), encoding="utf-8")
        except OSError:
            pass

    def add_recent_app(self, executable_path: str) -> None:
        self.recent_apps = [path for path in self.recent_apps if path.lower() != executable_path.lower()]
        self.recent_apps.insert(0, executable_path)
        del self.recent_apps[RECENT_APP_LIMIT:]
        self.save_recent_apps()

    def clear_recent_apps(self) -> None:
        self.recent_apps.clear()
        self.save_recent_apps()

    def load_settings(self) -> None:
        self.play_sound_on_hide = False
        self.menu_language = CHINESE_MENU_LANGUAGE
        try:
            if not self.settings_file.exists():
                return
            for line in self.settings_file.read_text(encoding="utf-8").splitlines():
                if "=" not in line:
                    continue
                key, value = [part.strip() for part in line.split("=", 1)]
                if key.lower() == PLAY_SOUND_ON_HIDE_KEY.lower():
                    self.play_sound_on_hide = value.lower() == "true"
                elif key.lower() == MENU_LANGUAGE_KEY.lower() and value.lower() == CHINESE_MENU_LANGUAGE.lower():
                    self.menu_language = CHINESE_MENU_LANGUAGE
        except OSError:
            self.play_sound_on_hide = False
            self.menu_language = CHINESE_MENU_LANGUAGE

    def save_settings(self) -> None:
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(
                f"{PLAY_SOUND_ON_HIDE_KEY}={self.play_sound_on_hide}\n{MENU_LANGUAGE_KEY}={self.menu_language}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def toggle_startup(self) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            ) as key:
                if is_startup_enabled():
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
                    self.show_balloon("已关闭开机自动启动。")
                else:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
                    self.show_balloon("已设置 TrayPocket 开机自动启动。")
        except OSError as exc:
            self.show_balloon(f"无法修改启动项设置：{exc}")

    def toggle_hide_sound(self) -> None:
        self.play_sound_on_hide = not self.play_sound_on_hide
        self.save_settings()
        self.show_balloon("已开启隐藏提示音。" if self.play_sound_on_hide else "已关闭隐藏提示音。")

    def is_chinese_menu(self) -> bool:
        return self.menu_language.lower() == CHINESE_MENU_LANGUAGE.lower()

    def use_chinese_menu(self) -> None:
        self.menu_language = CHINESE_MENU_LANGUAGE
        self.save_settings()
        self.show_balloon("已使用中文（简体）菜单。")

    def play_hide_sound(self) -> None:
        if self.play_sound_on_hide:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except RuntimeError:
                pass

    def open_config_folder(self) -> None:
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["explorer.exe", str(self.config_dir)])
        except OSError as exc:
            self.show_balloon(f"无法打开配置文件夹：{exc}")

    def show_balloon(self, message: str) -> None:
        nid = self._base_notify_data(MAIN_ICON_ID)
        nid.uFlags = NIF_INFO
        nid.szInfo = message[:255]
        nid.szInfoTitle = APP_NAME
        nid.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _handle_copy_data(self, lparam: int) -> None:
        try:
            cds = ctypes.cast(lparam, ctypes.POINTER(COPYDATASTRUCT)).contents
            text = ctypes.wstring_at(cds.lpData)
            for line in text.splitlines():
                path = line.strip()
                if path:
                    self.start_program_to_tray(path)
        except Exception:
            pass

    def exit(self) -> None:
        self.disposed = True
        self.restore_all_hidden_windows()
        for item in list(self.items):
            self.dispose_item(item)
        self._remove_tray_icon(MAIN_ICON_ID)
        user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)


def short_tray_text(text: str) -> str:
    if not text:
        return APP_NAME
    return text if len(text) <= 63 else text[:60] + "..."


def filename_or_fallback(path: str, fallback: str) -> str:
    try:
        if path:
            name = Path(path).stem
            if name:
                return name
    except OSError:
        pass
    return fallback


def extract_icon(executable_path: str) -> int:
    if executable_path and Path(executable_path).exists():
        hicon = shell32.ExtractIconW(None, executable_path, 0)
        if hicon:
            return hicon
    return user32.LoadIconW(None, ctypes.c_wchar_p(32512))


def get_window_title(window: int) -> str:
    length = user32.GetWindowTextLengthW(window)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(window, buffer, len(buffer))
    return buffer.value


def get_class_name(window: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(window, buffer, len(buffer))
    return buffer.value


def get_window_process_id(window: int) -> int:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    return int(process_id.value)


def find_main_window_for_pid(pid: int) -> int:
    found = {"hwnd": 0}

    def callback(hwnd: int, _lparam: int) -> bool:
        if found["hwnd"]:
            return False
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
            return True
        if get_window_process_id(hwnd) == pid:
            found["hwnd"] = hwnd
            return False
        return True

    user32.EnumWindows(ENUMWINDOWSPROC(callback), 0)
    return found["hwnd"]


def wait_for_main_window(process: subprocess.Popen, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return 0
        window = find_main_window_for_pid(process.pid)
        if window:
            return window
        time.sleep(0.25)
    return 0


def executable_path_for_pid(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def open_file_location(executable_path: str) -> None:
    if executable_path and Path(executable_path).exists():
        subprocess.Popen(["explorer.exe", f"/select,{executable_path}"])


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else exe
    return f'"{launcher}" "{Path(__file__).resolve()}"'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _value_type = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def send_args_to_existing_instance(args: list[str]) -> bool:
    hwnd = user32.FindWindowW(WINDOW_CLASS, None)
    if not hwnd:
        return False

    text = "\n".join(args)
    buffer = ctypes.create_unicode_buffer(text)
    cds = COPYDATASTRUCT()
    cds.dwData = 1
    cds.cbData = ctypes.sizeof(buffer)
    cds.lpData = ctypes.cast(buffer, ctypes.c_void_p)
    user32.SendMessageW(hwnd, WM_COPYDATA, 0, ctypes.addressof(cds))
    return True


def main(argv: list[str]) -> int:
    if os.name != "nt":
        print("TrayPocket only supports Windows.", file=sys.stderr)
        return 1

    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    already_running = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    if already_running:
        if argv and send_args_to_existing_instance(argv):
            return 0
        user32.MessageBoxW(None, "TrayPocket 已经在运行。请使用右下角托盘图标菜单。", APP_NAME, 0x40)
        return 0

    try:
        app = TrayPocketApp(argv)
        app.run()
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

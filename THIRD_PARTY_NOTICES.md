# 第三方来源说明

## fcFn/traymond

- 项目地址：https://github.com/fcFn/traymond
- 原项目协议：MIT License
- 原项目定位：一个把 Windows 窗口最小化/隐藏到系统托盘的小工具。

TrayPocket 参考了 Traymond 的交互思路：

- 用全局热键触发隐藏当前窗口。
- 为被隐藏窗口创建托盘图标。
- 双击托盘图标恢复窗口。
- 退出工具时恢复隐藏窗口。

TrayPocket 是重新实现的 C# WinForms 项目，没有直接复制 Traymond 的 C++ 源码。新增功能包括选择程序后直接托盘运行、最近程序列表、单实例命令转发、后台进程托管、开机启动开关和中文文档。

using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Media;
using System.Text;
using System.Threading;
using System.Windows.Forms;

// TrayPocket 是一个 Windows 托盘驻留工具。
// 设计灵感来自 fcFn/traymond：把窗口隐藏到系统托盘，并通过托盘图标恢复。
// 本项目没有复用 Traymond 的 C++ 源码，而是用 C# WinForms 重新实现，并加入“选择程序后一键托盘运行”等能力。
internal static class Program
{
    internal const string AppName = "TrayPocket";
    internal const string MutexName = "TrayPocket.SingleInstance.Mutex";
    internal const string PipeName = "TrayPocket.CommandPipe";

    [STAThread]
    private static void Main(string[] args)
    {
        bool createdNew;
        using (Mutex mutex = new Mutex(true, MutexName, out createdNew))
        {
            if (!createdNew)
            {
                // 已有实例运行时，把命令行里的程序路径转交给现有实例处理，避免重复出现多个主托盘图标。
                if (args.Length > 0 && SendArgsToExistingInstance(args))
                {
                    return;
                }

                MessageBox.Show(
                    "TrayPocket 已经在运行。请使用右下角托盘图标菜单。",
                    AppName,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new TrayPocketContext(args));

            GC.KeepAlive(mutex);
        }
    }

    private static bool SendArgsToExistingInstance(string[] args)
    {
        try
        {
            // 使用命名管道做轻量级进程间通信：第二次启动 exe 时，路径会发送给第一个实例。
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.Out))
            {
                pipe.Connect(1200);
                using (StreamWriter writer = new StreamWriter(pipe, new UTF8Encoding(false)))
                {
                    writer.AutoFlush = true;
                    for (int i = 0; i < args.Length; i++)
                    {
                        writer.WriteLine(args[i]);
                    }
                }
            }

            return true;
        }
        catch
        {
            return false;
        }
    }
}

internal sealed class TrayPocketContext : ApplicationContext
{
    private const string ConfigFileName = "apps.txt";
    private const string SettingsFileName = "settings.txt";
    private const string PlaySoundOnHideKey = "PlaySoundOnHide";
    private const string MenuLanguageKey = "MenuLanguage";
    private const string ChineseMenuLanguage = "zh-CN";
    private const int RecentAppLimit = 20;

    private readonly NotifyIcon mainIcon;
    private readonly ContextMenuStrip mainMenu;
    private readonly HotkeyWindow hotkeyWindow;
    private readonly Control invoker;
    private readonly List<TrayedItem> items;
    private readonly List<string> recentApps;
    private readonly string configDir;
    private readonly string configFile;
    private readonly string settingsFile;
    private readonly System.Windows.Forms.Timer monitorTimer;
    private int nextItemId;
    private bool playSoundOnHide;
    private string menuLanguage;
    private bool disposed;

    internal TrayPocketContext(string[] startupArgs)
    {
        items = new List<TrayedItem>();
        recentApps = new List<string>();
        nextItemId = 1;

        // 最近启动的程序保存在用户目录，不写入程序安装目录，方便普通权限运行。
        configDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            Program.AppName);
        configFile = Path.Combine(configDir, ConfigFileName);
        settingsFile = Path.Combine(configDir, SettingsFileName);
        LoadRecentApps();
        LoadSettings();

        // 后台线程需要把操作切回 WinForms UI 线程，这个隐藏控件只用于安全地 BeginInvoke。
        invoker = new Control();
        invoker.CreateControl();

        mainMenu = new ContextMenuStrip();
        mainMenu.Opening += delegate { RebuildMainMenu(); };

        mainIcon = new NotifyIcon();
        mainIcon.Icon = SystemIcons.Application;
        mainIcon.Text = Program.AppName;
        mainIcon.Visible = true;
        mainIcon.ContextMenuStrip = mainMenu;
        mainIcon.DoubleClick += delegate { SelectAndStartProgram(); };

        RebuildMainMenu();

        // 模仿 Traymond 的核心交互：Win + Shift + Z 把当前前台窗口隐藏到托盘。
        hotkeyWindow = new HotkeyWindow(delegate { HideForegroundWindowToTray(); });
        if (!hotkeyWindow.Registered)
        {
            ShowBalloon("Win+Shift+Z 已被占用。托盘菜单仍可正常使用。");
        }

        // 定期清理已经退出的程序，防止托盘残留无效图标。
        monitorTimer = new System.Windows.Forms.Timer();
        monitorTimer.Interval = 2000;
        monitorTimer.Tick += delegate { MonitorItems(); };
        monitorTimer.Start();

        StartPipeServer();

        for (int i = 0; i < startupArgs.Length; i++)
        {
            string path = startupArgs[i];
            if (!string.IsNullOrWhiteSpace(path))
            {
                StartProgramToTray(path);
            }
        }
    }

    private void RebuildMainMenu()
    {
        mainMenu.Items.Clear();

        ToolStripMenuItem runProgram = new ToolStripMenuItem("选择程序并托盘运行...");
        runProgram.Click += delegate { SelectAndStartProgram(); };
        mainMenu.Items.Add(runProgram);

        ToolStripMenuItem recent = new ToolStripMenuItem("最近程序一键托盘运行");
        if (recentApps.Count == 0)
        {
            recent.Enabled = false;
        }
        else
        {
            for (int i = 0; i < recentApps.Count; i++)
            {
                string appPath = recentApps[i];
                ToolStripMenuItem item = new ToolStripMenuItem(Path.GetFileNameWithoutExtension(appPath));
                item.ToolTipText = appPath;
                item.Click += delegate { StartProgramToTray(appPath); };
                recent.DropDownItems.Add(item);
            }
        }
        mainMenu.Items.Add(recent);

        mainMenu.Items.Add(new ToolStripSeparator());

        ToolStripMenuItem hideActive = new ToolStripMenuItem("隐藏当前窗口到托盘 (Win+Shift+Z)");
        hideActive.Click += delegate { HideForegroundWindowToTray(); };
        mainMenu.Items.Add(hideActive);

        ToolStripMenuItem restoreAll = new ToolStripMenuItem("恢复全部隐藏窗口 (" + HiddenWindowCount().ToString() + ")");
        restoreAll.Enabled = HiddenWindowCount() > 0;
        restoreAll.Click += delegate { RestoreAllHiddenWindows(); };
        mainMenu.Items.Add(restoreAll);

        if (items.Count > 0)
        {
            ToolStripMenuItem managed = new ToolStripMenuItem("当前托管项目");
            for (int i = 0; i < items.Count; i++)
            {
                TrayedItem trayedItem = items[i];
                ToolStripMenuItem item = new ToolStripMenuItem(trayedItem.Title);
                item.ToolTipText = trayedItem.ExecutablePath;
                item.Click += delegate { RestoreOrFocusItem(trayedItem); };
                managed.DropDownItems.Add(item);
            }
            mainMenu.Items.Add(managed);
        }

        mainMenu.Items.Add(new ToolStripSeparator());

        ToolStripMenuItem settings = new ToolStripMenuItem("设置");

        ToolStripMenuItem startup = new ToolStripMenuItem("开机自动启动 TrayPocket");
        startup.Checked = IsStartupEnabled();
        startup.Click += delegate { ToggleStartup(); };
        settings.DropDownItems.Add(startup);

        ToolStripMenuItem hideSound = new ToolStripMenuItem("隐藏程序时播放提示音");
        hideSound.Checked = playSoundOnHide;
        hideSound.Click += delegate { ToggleHideSound(); };
        settings.DropDownItems.Add(hideSound);

        ToolStripMenuItem language = new ToolStripMenuItem("菜单语言");
        ToolStripMenuItem chineseLanguage = new ToolStripMenuItem("中文（简体）");
        chineseLanguage.Checked = IsChineseMenu();
        chineseLanguage.Click += delegate { UseChineseMenu(); };
        language.DropDownItems.Add(chineseLanguage);
        settings.DropDownItems.Add(language);

        ToolStripMenuItem openConfig = new ToolStripMenuItem("打开配置文件夹");
        openConfig.Click += delegate { OpenConfigFolder(); };
        settings.DropDownItems.Add(openConfig);

        mainMenu.Items.Add(settings);

        ToolStripMenuItem clearRecent = new ToolStripMenuItem("清空最近程序");
        clearRecent.Enabled = recentApps.Count > 0;
        clearRecent.Click += delegate
        {
            recentApps.Clear();
            SaveRecentApps();
            RebuildMainMenu();
        };
        mainMenu.Items.Add(clearRecent);

        mainMenu.Items.Add(new ToolStripSeparator());

        ToolStripMenuItem exit = new ToolStripMenuItem("退出并恢复隐藏窗口");
        exit.Click += delegate { ExitThread(); };
        mainMenu.Items.Add(exit);
    }

    private void SelectAndStartProgram()
    {
        using (OpenFileDialog dialog = new OpenFileDialog())
        {
            dialog.Title = "选择要托盘运行的程序";
            dialog.Filter = "程序 (*.exe)|*.exe|所有文件 (*.*)|*.*";
            dialog.CheckFileExists = true;
            dialog.Multiselect = false;

            if (dialog.ShowDialog() == DialogResult.OK)
            {
                StartProgramToTray(dialog.FileName);
            }
        }
    }

    private void StartProgramToTray(string path)
    {
        string executablePath = Environment.ExpandEnvironmentVariables(path.Trim().Trim('"'));
        if (!File.Exists(executablePath))
        {
            ShowBalloon("找不到程序：" + executablePath);
            return;
        }

        AddRecentApp(executablePath);

        try
        {
            // 先正常启动程序，再等待它创建主窗口；有窗口则隐藏，无窗口则按后台进程托管。
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = executablePath;
            info.WorkingDirectory = Path.GetDirectoryName(executablePath);
            info.UseShellExecute = true;

            Process process = Process.Start(info);
            if (process == null)
            {
                ShowBalloon("无法启动：" + Path.GetFileName(executablePath));
                return;
            }

            ThreadPool.QueueUserWorkItem(delegate
            {
                IntPtr window = WaitForMainWindow(process, 15000);
                OnUi(delegate
                {
                    if (disposed)
                    {
                        return;
                    }

                    if (window != IntPtr.Zero && NativeMethods.IsWindow(window))
                    {
                        AddWindowToTray(window, process, executablePath, true);
                    }
                    else
                    {
                        AddBackgroundProcessToTray(process, executablePath);
                    }
                });
            });
        }
        catch (Exception ex)
        {
            ShowBalloon("无法启动 " + Path.GetFileName(executablePath) + "：" + ex.Message);
        }
    }

    private void HideForegroundWindowToTray()
    {
        IntPtr window = NativeMethods.GetForegroundWindow();
        if (!CanHideWindow(window))
        {
            ShowBalloon("当前没有可隐藏的普通窗口。");
            return;
        }

        Process process = TryGetProcessForWindow(window);
        if (process != null && process.Id == Process.GetCurrentProcess().Id)
        {
            return;
        }

        string executablePath = TryGetExecutablePath(process);
        AddWindowToTray(window, process, executablePath, false);
    }

    private bool CanHideWindow(IntPtr window)
    {
        if (window == IntPtr.Zero)
        {
            return false;
        }

        if (window == NativeMethods.GetDesktopWindow() || window == NativeMethods.GetShellWindow())
        {
            return false;
        }

        if (!NativeMethods.IsWindow(window) || !NativeMethods.IsWindowVisible(window))
        {
            return false;
        }

        string className = GetClassName(window);
        // 这些是 Windows 桌面、任务栏或特殊系统窗口，隐藏它们会破坏桌面体验。
        if (className == "Shell_TrayWnd" ||
            className == "WorkerW" ||
            className == "Progman" ||
            className == "Button")
        {
            return false;
        }

        return FindItemByWindow(window) == null;
    }

    private void AddWindowToTray(IntPtr window, Process process, string executablePath, bool startedByTrayPocket)
    {
        if (!CanHideWindow(window))
        {
            ShowBalloon("这个窗口不能隐藏到托盘。");
            return;
        }

        string title = GetWindowTitle(window);
        if (string.IsNullOrWhiteSpace(title))
        {
            title = FileNameOrFallback(executablePath, "隐藏窗口");
        }

        TrayedItem item = new TrayedItem();
        item.Id = nextItemId++;
        item.WindowHandle = window;
        item.Process = process;
        item.ExecutablePath = executablePath;
        item.Title = title;
        item.StartedByTrayPocket = startedByTrayPocket;
        item.IconImage = ExtractIcon(executablePath);
        item.NotifyIcon = CreateNotifyIcon(item);

        items.Add(item);
        NativeMethods.ShowWindow(window, NativeMethods.SW_HIDE);
        PlayHideSound();
        ShowBalloon("已隐藏到托盘：" + item.Title);
    }

    private void AddBackgroundProcessToTray(Process process, string executablePath)
    {
        TrayedItem item = new TrayedItem();
        item.Id = nextItemId++;
        item.WindowHandle = IntPtr.Zero;
        item.Process = process;
        item.ExecutablePath = executablePath;
        item.Title = FileNameOrFallback(executablePath, "后台进程");
        item.StartedByTrayPocket = true;
        item.IconImage = ExtractIcon(executablePath);
        item.NotifyIcon = CreateNotifyIcon(item);

        items.Add(item);
        ShowBalloon("已作为后台进程托管：" + item.Title);
    }

    private NotifyIcon CreateNotifyIcon(TrayedItem item)
    {
        NotifyIcon icon = new NotifyIcon();
        icon.Icon = item.IconImage;
        icon.Text = ShortTrayText(item.Title);
        icon.Visible = true;
        icon.ContextMenuStrip = CreateItemMenu(item);
        icon.DoubleClick += delegate { RestoreOrFocusItem(item); };
        return icon;
    }

    private ContextMenuStrip CreateItemMenu(TrayedItem item)
    {
        ContextMenuStrip menu = new ContextMenuStrip();

        ToolStripMenuItem restore = new ToolStripMenuItem(item.WindowHandle == IntPtr.Zero ? "查找窗口 / 聚焦" : "恢复窗口");
        restore.Click += delegate { RestoreOrFocusItem(item); };
        menu.Items.Add(restore);

        ToolStripMenuItem openLocation = new ToolStripMenuItem("打开文件所在位置");
        openLocation.Enabled = !string.IsNullOrEmpty(item.ExecutablePath) && File.Exists(item.ExecutablePath);
        openLocation.Click += delegate { OpenFileLocation(item.ExecutablePath); };
        menu.Items.Add(openLocation);

        if (item.WindowHandle == IntPtr.Zero)
        {
            ToolStripMenuItem stop = new ToolStripMenuItem("结束进程");
            stop.Click += delegate { StopProcessItem(item); };
            menu.Items.Add(stop);

            ToolStripMenuItem remove = new ToolStripMenuItem("移除托盘图标");
            remove.Click += delegate { DisposeItem(item); };
            menu.Items.Add(remove);
        }

        return menu;
    }

    private void RestoreOrFocusItem(TrayedItem item)
    {
        if (!items.Contains(item))
        {
            return;
        }

        if (item.WindowHandle != IntPtr.Zero && NativeMethods.IsWindow(item.WindowHandle))
        {
            NativeMethods.ShowWindow(item.WindowHandle, NativeMethods.SW_RESTORE);
            NativeMethods.ShowWindow(item.WindowHandle, NativeMethods.SW_SHOW);
            NativeMethods.SetForegroundWindow(item.WindowHandle);
            DisposeItem(item);
            return;
        }

        IntPtr window = FindMainWindowForProcess(item.Process);
        if (window != IntPtr.Zero)
        {
            item.WindowHandle = window;
            NativeMethods.ShowWindow(window, NativeMethods.SW_RESTORE);
            NativeMethods.ShowWindow(window, NativeMethods.SW_SHOW);
            NativeMethods.SetForegroundWindow(window);
        }
        else
        {
            ShowBalloon("没有找到可见窗口：" + item.Title);
        }
    }

    private void RestoreAllHiddenWindows()
    {
        TrayedItem[] snapshot = items.ToArray();
        for (int i = 0; i < snapshot.Length; i++)
        {
            TrayedItem item = snapshot[i];
            if (item.WindowHandle != IntPtr.Zero && NativeMethods.IsWindow(item.WindowHandle))
            {
                NativeMethods.ShowWindow(item.WindowHandle, NativeMethods.SW_RESTORE);
                NativeMethods.ShowWindow(item.WindowHandle, NativeMethods.SW_SHOW);
                DisposeItem(item);
            }
        }
    }

    private void StopProcessItem(TrayedItem item)
    {
        if (item.Process == null)
        {
            DisposeItem(item);
            return;
        }

        DialogResult result = MessageBox.Show(
            "确定要结束 " + item.Title + " 吗？",
            Program.AppName,
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Question);
        if (result != DialogResult.Yes)
        {
            return;
        }

        try
        {
            if (!item.Process.HasExited)
            {
                item.Process.CloseMainWindow();
                if (!item.Process.WaitForExit(2500))
                {
                    item.Process.Kill();
                }
            }
        }
        catch (Exception ex)
        {
            ShowBalloon("无法结束 " + item.Title + "：" + ex.Message);
            return;
        }

        DisposeItem(item);
    }

    private void MonitorItems()
    {
        TrayedItem[] snapshot = items.ToArray();
        for (int i = 0; i < snapshot.Length; i++)
        {
            TrayedItem item = snapshot[i];
            // 如果窗口已被程序自身关闭，就同步移除对应托盘图标。
            if (item.WindowHandle != IntPtr.Zero && !NativeMethods.IsWindow(item.WindowHandle))
            {
                DisposeItem(item);
                continue;
            }

            if (item.WindowHandle == IntPtr.Zero && item.Process != null)
            {
                try
                {
                    if (item.Process.HasExited)
                    {
                        DisposeItem(item);
                    }
                }
                catch
                {
                    DisposeItem(item);
                }
            }
        }
    }

    private void DisposeItem(TrayedItem item)
    {
        if (!items.Remove(item))
        {
            return;
        }

        if (item.NotifyIcon != null)
        {
            item.NotifyIcon.Visible = false;
            item.NotifyIcon.Dispose();
            item.NotifyIcon = null;
        }

        if (item.IconImage != null)
        {
            item.IconImage.Dispose();
            item.IconImage = null;
        }
    }

    private TrayedItem FindItemByWindow(IntPtr window)
    {
        for (int i = 0; i < items.Count; i++)
        {
            if (items[i].WindowHandle == window)
            {
                return items[i];
            }
        }

        return null;
    }

    private int HiddenWindowCount()
    {
        int count = 0;
        for (int i = 0; i < items.Count; i++)
        {
            if (items[i].WindowHandle != IntPtr.Zero)
            {
                count++;
            }
        }

        return count;
    }

    private static IntPtr WaitForMainWindow(Process process, int timeoutMilliseconds)
    {
        DateTime deadline = DateTime.UtcNow.AddMilliseconds(timeoutMilliseconds);
        while (DateTime.UtcNow < deadline)
        {
            // 部分程序启动较慢，MainWindowHandle 需要轮询几秒后才会出现。
            IntPtr window = FindMainWindowForProcess(process);
            if (window != IntPtr.Zero)
            {
                return window;
            }

            try
            {
                if (process.HasExited)
                {
                    return IntPtr.Zero;
                }
            }
            catch
            {
                return IntPtr.Zero;
            }

            Thread.Sleep(250);
        }

        return IntPtr.Zero;
    }

    private static IntPtr FindMainWindowForProcess(Process process)
    {
        if (process == null)
        {
            return IntPtr.Zero;
        }

        try
        {
            process.Refresh();
            if (process.MainWindowHandle != IntPtr.Zero && NativeMethods.IsWindow(process.MainWindowHandle))
            {
                return process.MainWindowHandle;
            }
        }
        catch
        {
            return IntPtr.Zero;
        }

        return IntPtr.Zero;
    }

    private static Process TryGetProcessForWindow(IntPtr window)
    {
        try
        {
            uint processId;
            NativeMethods.GetWindowThreadProcessId(window, out processId);
            if (processId == 0)
            {
                return null;
            }

            return Process.GetProcessById((int)processId);
        }
        catch
        {
            return null;
        }
    }

    private static string TryGetExecutablePath(Process process)
    {
        try
        {
            if (process != null && process.MainModule != null)
            {
                return process.MainModule.FileName;
            }
        }
        catch
        {
        }

        return null;
    }

    private static string GetWindowTitle(IntPtr window)
    {
        StringBuilder builder = new StringBuilder(512);
        NativeMethods.GetWindowText(window, builder, builder.Capacity);
        return builder.ToString();
    }

    private static string GetClassName(IntPtr window)
    {
        StringBuilder builder = new StringBuilder(256);
        NativeMethods.GetClassName(window, builder, builder.Capacity);
        return builder.ToString();
    }

    private static string FileNameOrFallback(string path, string fallback)
    {
        try
        {
            if (!string.IsNullOrEmpty(path))
            {
                string name = Path.GetFileNameWithoutExtension(path);
                if (!string.IsNullOrEmpty(name))
                {
                    return name;
                }
            }
        }
        catch
        {
        }

        return fallback;
    }

    private static Icon ExtractIcon(string executablePath)
    {
        try
        {
            if (!string.IsNullOrEmpty(executablePath) && File.Exists(executablePath))
            {
                Icon icon = Icon.ExtractAssociatedIcon(executablePath);
                if (icon != null)
                {
                    return (Icon)icon.Clone();
                }
            }
        }
        catch
        {
        }

        return (Icon)SystemIcons.Application.Clone();
    }

    private static string ShortTrayText(string text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return Program.AppName;
        }

        return text.Length > 63 ? text.Substring(0, 60) + "..." : text;
    }

    private void AddRecentApp(string executablePath)
    {
        // 最近程序列表按“最近使用”排序，同一个路径只保留一条。
        for (int i = recentApps.Count - 1; i >= 0; i--)
        {
            if (string.Equals(recentApps[i], executablePath, StringComparison.OrdinalIgnoreCase))
            {
                recentApps.RemoveAt(i);
            }
        }

        recentApps.Insert(0, executablePath);
        while (recentApps.Count > RecentAppLimit)
        {
            recentApps.RemoveAt(recentApps.Count - 1);
        }

        SaveRecentApps();
    }

    private void LoadRecentApps()
    {
        recentApps.Clear();
        try
        {
            if (!File.Exists(configFile))
            {
                return;
            }

            string[] lines = File.ReadAllLines(configFile, Encoding.UTF8);
            for (int i = 0; i < lines.Length; i++)
            {
                string path = lines[i].Trim();
                if (path.Length > 0 && File.Exists(path))
                {
                    recentApps.Add(path);
                }
            }
        }
        catch
        {
        }
    }

    private void SaveRecentApps()
    {
        try
        {
            Directory.CreateDirectory(configDir);
            File.WriteAllLines(configFile, recentApps.ToArray(), new UTF8Encoding(false));
        }
        catch
        {
        }
    }

    private void LoadSettings()
    {
        playSoundOnHide = false;
        menuLanguage = ChineseMenuLanguage;

        try
        {
            if (!File.Exists(settingsFile))
            {
                return;
            }

            string[] lines = File.ReadAllLines(settingsFile, Encoding.UTF8);
            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].Trim();
                int separator = line.IndexOf('=');
                if (separator <= 0)
                {
                    continue;
                }

                string key = line.Substring(0, separator).Trim();
                string value = line.Substring(separator + 1).Trim();
                if (string.Equals(key, PlaySoundOnHideKey, StringComparison.OrdinalIgnoreCase))
                {
                    bool parsed;
                    if (bool.TryParse(value, out parsed))
                    {
                        playSoundOnHide = parsed;
                    }
                }
                else if (string.Equals(key, MenuLanguageKey, StringComparison.OrdinalIgnoreCase))
                {
                    if (string.Equals(value, ChineseMenuLanguage, StringComparison.OrdinalIgnoreCase))
                    {
                        menuLanguage = ChineseMenuLanguage;
                    }
                }
            }
        }
        catch
        {
            playSoundOnHide = false;
            menuLanguage = ChineseMenuLanguage;
        }
    }

    private void SaveSettings()
    {
        try
        {
            Directory.CreateDirectory(configDir);
            string[] lines = new string[]
            {
                PlaySoundOnHideKey + "=" + playSoundOnHide.ToString(),
                MenuLanguageKey + "=" + menuLanguage
            };
            File.WriteAllLines(settingsFile, lines, new UTF8Encoding(false));
        }
        catch
        {
        }
    }

    private static string StartupRegistryPath
    {
        get { return @"Software\Microsoft\Windows\CurrentVersion\Run"; }
    }

    private static bool IsStartupEnabled()
    {
        try
        {
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(StartupRegistryPath, false))
            {
                string value = key == null ? null : key.GetValue(Program.AppName) as string;
                return !string.IsNullOrEmpty(value);
            }
        }
        catch
        {
            return false;
        }
    }

    private void ToggleStartup()
    {
        try
        {
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(StartupRegistryPath, true))
            {
                if (key == null)
                {
                    ShowBalloon("无法打开 Windows 启动项设置。");
                    return;
                }

                if (IsStartupEnabled())
                {
                    key.DeleteValue(Program.AppName, false);
                    ShowBalloon("已关闭开机自动启动。");
                }
                else
                {
                    key.SetValue(Program.AppName, "\"" + Application.ExecutablePath + "\"");
                    ShowBalloon("已设置 TrayPocket 开机自动启动。");
                }
            }
        }
        catch (Exception ex)
        {
            ShowBalloon("无法修改启动项设置：" + ex.Message);
        }
    }

    private void ToggleHideSound()
    {
        playSoundOnHide = !playSoundOnHide;
        SaveSettings();
        RebuildMainMenu();
        ShowBalloon(playSoundOnHide ? "已开启隐藏提示音。" : "已关闭隐藏提示音。");
    }

    private bool IsChineseMenu()
    {
        return string.Equals(menuLanguage, ChineseMenuLanguage, StringComparison.OrdinalIgnoreCase);
    }

    private void UseChineseMenu()
    {
        menuLanguage = ChineseMenuLanguage;
        SaveSettings();
        RebuildMainMenu();
        ShowBalloon("已使用中文（简体）菜单。");
    }

    private void PlayHideSound()
    {
        if (!playSoundOnHide)
        {
            return;
        }

        try
        {
            SystemSounds.Asterisk.Play();
        }
        catch
        {
        }
    }

    private void OpenConfigFolder()
    {
        try
        {
            Directory.CreateDirectory(configDir);
            Process.Start("explorer.exe", configDir);
        }
        catch (Exception ex)
        {
            ShowBalloon("无法打开配置文件夹：" + ex.Message);
        }
    }

    private static void OpenFileLocation(string executablePath)
    {
        try
        {
            if (!string.IsNullOrEmpty(executablePath) && File.Exists(executablePath))
            {
                Process.Start("explorer.exe", "/select,\"" + executablePath + "\"");
            }
        }
        catch
        {
        }
    }

    private void StartPipeServer()
    {
        // 后台管道服务用于接收后续 TrayPocket.exe 调用传来的程序路径。
        Thread thread = new Thread(PipeServerLoop);
        thread.IsBackground = true;
        thread.Start();
    }

    private void PipeServerLoop()
    {
        while (!disposed)
        {
            try
            {
                using (NamedPipeServerStream pipe = new NamedPipeServerStream(Program.PipeName, PipeDirection.In))
                {
                    pipe.WaitForConnection();
                    using (StreamReader reader = new StreamReader(pipe, Encoding.UTF8))
                    {
                        string line;
                        while ((line = reader.ReadLine()) != null)
                        {
                            string requestedPath = line.Trim();
                            if (requestedPath.Length > 0)
                            {
                                OnUi(delegate { StartProgramToTray(requestedPath); });
                            }
                        }
                    }
                }
            }
            catch
            {
                Thread.Sleep(500);
            }
        }
    }

    private void OnUi(Action action)
    {
        if (disposed || invoker.IsDisposed)
        {
            return;
        }

        if (invoker.InvokeRequired)
        {
            try
            {
                invoker.BeginInvoke(action);
            }
            catch
            {
            }
        }
        else
        {
            action();
        }
    }

    private void ShowBalloon(string message)
    {
        try
        {
            mainIcon.ShowBalloonTip(3000, Program.AppName, message, ToolTipIcon.Info);
        }
        catch
        {
        }
    }

    protected override void ExitThreadCore()
    {
        disposed = true;
        monitorTimer.Stop();
        RestoreAllHiddenWindows();

        if (hotkeyWindow != null)
        {
            hotkeyWindow.Dispose();
        }

        if (mainIcon != null)
        {
            mainIcon.Visible = false;
            mainIcon.Dispose();
        }

        if (mainMenu != null)
        {
            mainMenu.Dispose();
        }

        if (invoker != null)
        {
            invoker.Dispose();
        }

        base.ExitThreadCore();
    }
}

internal sealed class TrayedItem
{
    // 一个 TrayedItem 对应一个被隐藏的窗口，或一个没有窗口但需要继续运行的后台进程。
    internal int Id;
    internal IntPtr WindowHandle;
    internal Process Process;
    internal string ExecutablePath;
    internal string Title;
    internal bool StartedByTrayPocket;
    internal NotifyIcon NotifyIcon;
    internal Icon IconImage;
}

internal sealed class HotkeyWindow : NativeWindow, IDisposable
{
    private const int HotkeyId = 0x5450;
    private readonly Action onHotkey;
    private bool registered;

    internal HotkeyWindow(Action onHotkey)
    {
        this.onHotkey = onHotkey;
        CreateHandle(new CreateParams());
        // RegisterHotKey 需要一个窗口句柄；NativeWindow 提供了无需显示界面的消息窗口。
        registered = NativeMethods.RegisterHotKey(
            Handle,
            HotkeyId,
            NativeMethods.MOD_WIN | NativeMethods.MOD_SHIFT | NativeMethods.MOD_NOREPEAT,
            (uint)Keys.Z);
    }

    internal bool Registered
    {
        get { return registered; }
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == NativeMethods.WM_HOTKEY && m.WParam.ToInt32() == HotkeyId)
        {
            if (onHotkey != null)
            {
                onHotkey();
            }
            return;
        }

        base.WndProc(ref m);
    }

    public void Dispose()
    {
        if (registered)
        {
            NativeMethods.UnregisterHotKey(Handle, HotkeyId);
            registered = false;
        }

        DestroyHandle();
    }
}

internal static class NativeMethods
{
    // 这里只封装少量 Win32 API：热键、前台窗口、显示/隐藏窗口、窗口标题和进程归属。
    internal const int WM_HOTKEY = 0x0312;
    internal const int SW_HIDE = 0;
    internal const int SW_SHOW = 5;
    internal const int SW_RESTORE = 9;
    internal const uint MOD_SHIFT = 0x0004;
    internal const uint MOD_WIN = 0x0008;
    internal const uint MOD_NOREPEAT = 0x4000;

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern IntPtr GetForegroundWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern bool SetForegroundWindow(IntPtr hWnd);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern bool IsWindow(IntPtr hWnd);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern bool IsWindowVisible(IntPtr hWnd);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern IntPtr GetDesktopWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern IntPtr GetShellWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto)]
    internal static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto)]
    internal static extern int GetClassName(IntPtr hWnd, StringBuilder className, int maxCount);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    internal static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}

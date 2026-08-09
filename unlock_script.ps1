# Winlogon SYSTEM Unlock Script for Rupankar Sir
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Generic;

public class SystemWinlogonUnlocker {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern IntPtr OpenDesktop(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);

    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetThreadDesktop(IntPtr hDesktop);

    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool CloseDesktop(IntPtr hDesktop);

    [DllImport("user32.dll")]
    public static extern short VkKeyScanW(char ch);

    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, uint dwExtraInfo);

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort wVk, wScan;
        public uint dwFlags, time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT {
        public int dx, dy, mouseData, dwFlags, time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct HARDWAREINPUT {
        public uint uMsg;
        public ushort wParamL, wParamH;
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct INPUT {
        [FieldOffset(0)] public int type;
        [FieldOffset(4)] public KEYBDINPUT ki;
        [FieldOffset(4)] public MOUSEINPUT mi;
        [FieldOffset(4)] public HARDWAREINPUT hi;
    }

    const uint GENERIC_ALL     = 0x10000000;
    const uint KEYEVENTF_KEYUP = 0x0002;
    const int  INPUT_KEYBOARD  = 1;

    static INPUT Key(ushort vk, bool up) {
        INPUT inp = new INPUT();
        inp.type = INPUT_KEYBOARD;
        inp.ki.wVk = vk;
        inp.ki.wScan = 0;
        inp.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
        return inp;
    }

    public static void PerformUnlock(string pwd) {
        IntPtr hDesk = OpenDesktop("Winlogon", 0, false, GENERIC_ALL);
        if (hDesk != IntPtr.Zero) {
            SetThreadDesktop(hDesk);
        }

        // Wake screen: Space + Enter
        keybd_event(0x20, 0, 0, 0); Thread.Sleep(40); keybd_event(0x20, 0, 2, 0);
        Thread.Sleep(100);
        keybd_event(0x0D, 0, 0, 0); Thread.Sleep(40); keybd_event(0x0D, 0, 2, 0);

        // Wait 2.5 seconds for wallpaper slide animation
        Thread.Sleep(2500);

        // Clear field: Backspace x 15
        for (int i = 0; i < 15; i++) {
            keybd_event(0x08, 0, 0, 0); Thread.Sleep(20); keybd_event(0x08, 0, 2, 0); Thread.Sleep(20);
        }
        Thread.Sleep(250);

        // Stream password: Rupankar9831480960
        foreach (char c in pwd) {
            short vkShift = VkKeyScanW(c);
            byte vk = (byte)(vkShift & 0xFF);
            bool shift = ((vkShift >> 8) & 1) == 1;

            if (shift) keybd_event(0x10, 0, 0, 0);
            keybd_event(vk, 0, 0, 0);
            Thread.Sleep(40);
            keybd_event(vk, 0, 2, 0);
            Thread.Sleep(40);
            if (shift) keybd_event(0x10, 0, 2, 0);
        }

        Thread.Sleep(400);

        // Submit with Enter
        keybd_event(0x0D, 0, 0, 0); Thread.Sleep(60); keybd_event(0x0D, 0, 2, 0);

        if (hDesk != IntPtr.Zero) CloseDesktop(hDesk);
    }
}
'@

$pwd = "Rupankar9831480960"
[SystemWinlogonUnlocker]::PerformUnlock($pwd)

import os
import subprocess
import shutil

def find_adb():
    adb_path = shutil.which("adb")
    if adb_path: return adb_path
    candidates = [
        r"C:\tenorshare\adb\adb.exe",
        r"C:\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\Program Files\platform-tools\adb.exe",
        r"C:\adb\adb.exe"
    ]
    for c in candidates:
        if os.path.exists(c): return c
    return None

def main():
    print("==================================================")
    print("      NEHA AI — WIRELESS ADB PHONE SETUP          ")
    print("==================================================")
    
    adb = find_adb()
    if not adb:
        print("\n[!] ADB tool not found on PATH.")
        print("    Download platform-tools from: https://developer.android.com/studio/releases/platform-tools")
        print("    Extract to C:\\platform-tools\\ and run this script again.\n")
        return

    print(f"\n[+] ADB Binary Found: {adb}")
    print("\nSelect Option:")
    print("1. Pair New Phone over Wi-Fi (First Time)")
    print("2. Connect to Already Paired Phone")
    print("3. Check Connected Devices")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    if choice == "1":
        ip_port = input("Enter Phone IP:Port shown on 'Pair device with pairing code' screen (e.g. 192.168.1.15:38291): ").strip()
        code = input("Enter 6-digit Wi-Fi Pairing Code: ").strip()
        print(f"\nRunning: adb pair {ip_port}...")
        res = subprocess.run([adb, "pair", ip_port, code], capture_output=True, text=True)
        print(res.stdout)
        print(res.stderr)
        
    elif choice == "2":
        ip = input("Enter Phone IP address (e.g. 192.168.1.15): ").strip()
        print(f"\nConnecting to {ip}:5555...")
        res = subprocess.run([adb, "connect", f"{ip}:5555"], capture_output=True, text=True)
        print(res.stdout)
        
    elif choice == "3":
        res = subprocess.run([adb, "devices"], capture_output=True, text=True)
        print("\n" + res.stdout)

if __name__ == "__main__":
    main()

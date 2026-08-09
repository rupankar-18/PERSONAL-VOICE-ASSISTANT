Set WshShell = WScript.CreateObject("WScript.Shell")

' Step 1: Wake display and dismiss lock screen wallpaper
WScript.Sleep 500
WshShell.SendKeys " "
WScript.Sleep 300
WshShell.SendKeys "{ENTER}"

' Step 2: Wait 2.5 seconds for lock screen swipe animation to finish and password box to gain focus
WScript.Sleep 2500

' Step 3: Clear any pre-existing text
For i = 1 To 10
    WshShell.SendKeys "{BACKSPACE}"
    WScript.Sleep 30
Next
WScript.Sleep 200

' Step 4: Type full password Rupankar9831480960
WshShell.SendKeys "Rupankar9831480960"
WScript.Sleep 500

' Step 5: Press Enter to log in
WshShell.SendKeys "{ENTER}"

' Step 6: Backup attempt 3 seconds later if Windows animation was slow
WScript.Sleep 3000
WshShell.SendKeys "^a"
WScript.Sleep 100
WshShell.SendKeys "{BACKSPACE}"
WScript.Sleep 100
WshShell.SendKeys "Rupankar9831480960"
WScript.Sleep 500
WshShell.SendKeys "{ENTER}"

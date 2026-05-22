Option Explicit

Dim shell, args, command, i
Set shell = CreateObject("WScript.Shell")
Set args = WScript.Arguments

If args.Count = 0 Then
    WScript.Quit 1
End If

command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & args(0) & Chr(34)

For i = 1 To args.Count - 1
    command = command & " " & Chr(34) & args(i) & Chr(34)
Next

shell.Run command, 0, False

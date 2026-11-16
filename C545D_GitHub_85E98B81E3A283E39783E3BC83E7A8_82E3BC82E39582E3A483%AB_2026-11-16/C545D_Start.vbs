Option Explicit
Dim fso, sh, folder, app, ps, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
app = fso.BuildPath(folder, "C545D_App.ps1")
If Not fso.FileExists(app) Then
    MsgBox "C545D_App.ps1 was not found. Please extract the entire ZIP.", 16, "C545D"
    WScript.Quit 1
End If
sh.Environment("PROCESS")("C545D_VIDEO_DECODER") = "avdec"
ps = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
command = """" & ps & """ -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & app & """"
sh.Run command, 0, False

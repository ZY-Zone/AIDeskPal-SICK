Option Explicit
Dim fso, here, src, root, python, data, args, shell, setup

Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
src = fso.GetParentFolderName(here)
root = fso.GetParentFolderName(src)
Set shell = CreateObject("Shell.Application")

python = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(python) Then
  python = root & "\.venv\Scripts\python.exe"
End If

If Not fso.FileExists(python) Then
  setup = root & "\bootstrap.cmd"
  If Not fso.FileExists(setup) Then
    MsgBox "bootstrap.cmd is missing. Re-download the project.", 16, "AIDeskPal-SICK"
    WScript.Quit 1
  End If
  ' First launch: show the dependency setup window, then it starts the app.
  shell.ShellExecute "cmd.exe", "/c """ & setup & """", root, "runas", 0
  WScript.Quit 0
End If

data = root & "\user_data"
args = "/c set ""PYTHONPATH=" & root & "\src"" && set ""AIDESKPAL_DATA_DIR=" & data & """ && """ & python & """ -m aideskpal"

' runas -> UAC administrator; 0 -> SW_HIDE, so no console window remains.
shell.ShellExecute "cmd.exe", args, root, "runas", 0


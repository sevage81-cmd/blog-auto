' Entry point called daily by Task Scheduler. Runs the pipeline with no topic
' prompt, using today's weekday topic (run.ps1 -Today sets it; CLAUDE.md maps
' the weekday to a fixed topic). Kept ASCII-only on purpose: .vbs is read as
' ANSI/CP949 and would mangle Korean literals.
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "\run.ps1"" -Today"
CreateObject("WScript.Shell").Run cmd, 0, False

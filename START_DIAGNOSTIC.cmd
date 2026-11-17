@echo off
setlocal DisableDelayedExpansion
rem C545D optional GStreamer diagnostic launcher.
rem This only sets logging for NEW child processes; it never modifies MP4.
rem DO NOT launch while an existing recorder is active.
set "C545D_LOGS=%LOCALAPPDATA%\C545D_GStreamer\Logs"
if not exist "%C545D_LOGS%" mkdir "%C545D_LOGS%"
rem Capture key elements at focused levels; avoid expensive full tracing.
set "GST_DEBUG=*:2,rtph264depay:5,h264parse:5,rtpjitterbuffer:4,qtmux:5,audiorate:4,splitmuxsink:4"
set "GST_DEBUG_NO_COLOR=1"
rem GStreamer replaces %%p and %%r with PID and random ID respectively.
rem Different gst-inspect/preflight/gst-launch subprocesses get their own files.
set "GST_DEBUG_FILE=%C545D_LOGS%\GST_DIAG_%%p_%%r.log"
if not exist "%~dp0C545D_Recorder.exe" (
  echo Recorder EXE not found. Extract the whole ZIP first.
  pause
  exit /b 1
)
echo Starting C545D with focused GStreamer debug logging.
echo Logs: %C545D_LOGS%
echo Debug logs may contain camera connection details. Review before sharing.
start "" "%~dp0C545D_Recorder.exe"
endlocal

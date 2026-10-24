@ECHO OFF
REM One-time setup of the offline server. Run from an administrator command prompt.
REM Needs the internet once (packages, Core3 source); the game itself never does.

SETLOCAL
SET "DISTRO=Debian"

wsl.exe --status >NUL 2>&1
IF ERRORLEVEL 1 (
  ECHO WSL is not installed. Installing it with %DISTRO%; Windows will ask to reboot.
  ECHO After the reboot, finish the %DISTRO% user setup, then run this script again.
  wsl.exe --install --distribution %DISTRO%
  GOTO :END
)

wsl.exe --list --quiet | FINDSTR /I /B /C:"%DISTRO%" >NUL
IF ERRORLEVEL 1 (
  REM wsl --list prints UTF-16, which FINDSTR may not match; ask WSL directly instead
  wsl.exe -d %DISTRO% -- true >NUL 2>&1
  IF ERRORLEVEL 1 (
    ECHO Installing %DISTRO%. Create a user when asked, then type: exit
    wsl.exe --install --distribution %DISTRO%
  )
)

ECHO Setting up the Core3 server inside WSL. This builds Core3 and takes a while.
wsl.exe -d %DISTRO% -u root --cd "%~dp0..\server\wsl" -- bash ./setup.sh %*
IF ERRORLEVEL 1 (
  ECHO Setup failed, see the messages above.
  GOTO :END
)

ECHO.
ECHO Done. Start the game with "SWG Offline.cmd" (or SWGOffline.exe if you built it).

:END
PAUSE
ENDLOCAL

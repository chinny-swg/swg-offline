@ECHO OFF
REM Builds dist\SWGOffline.exe, a single-file launcher that needs no Python install.
CD /D "%~dp0..\launcher"
python -m pip install --upgrade pyinstaller || GOTO :EOF
python -m PyInstaller --noconfirm --onefile --windowed --name SWGOffline --distpath "%~dp0..\dist" swg_offline_app.py

@ECHO OFF
REM Opens the launcher without a console window. Needs Python 3.9+ from python.org (its "pyw" launcher).
CD /D "%~dp0..\launcher"
START "" pyw -3 -m swg_offline %*

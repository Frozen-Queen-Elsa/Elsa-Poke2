@ECHO OFF
del /f "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe">nul 2>&1
FOR %%A in ("%PATH%:;=";"%") DO (
    echo %%~A | findstr "Python">nul 2>&1
    IF errorlevel 1 (cd .) else (GOTO :SKIP)
)

FOR %%a in (8 7) DO (
	IF EXIST "%LOCALAPPDATA%\Programs\Python\Python3%%a" (
		SET PYTHONPATH="%LOCALAPPDATA%\Programs\Python\Python3%%a"
		CALL :PATHHANDLER
		GOTO :EOF
	)
)

:PATHHANDLER
setlocal enabledelayedexpansion
set curr_path=!PYTHONPATH!
FOR /D %%B IN (%PYTHONPATH%\*) DO set curr_path=!curr_path!;"%%~fB"
setx PATH "!curr_path!"
setx PYTHONPATH "!curr_path!"
GOTO :FINISH

:FINISH
ECHO Finished Adding Python adding to PATH.
GOTO :FINAL
:SKIP
ECHO Good, Python is already added to the Path!
GOTO :ALT
:FINAL
"%PYTHONPATH%\python.exe" check_ver.py "%PYTHONPATH%\Scripts" "%~dp0\"
ECHO You may close this window now.
timeout -1
GOTO :EOF
:ALT
python check_ver.py
timeout -1
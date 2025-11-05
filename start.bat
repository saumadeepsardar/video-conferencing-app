@ECHO OFF

:: --- Activate the virtual environment ---
ECHO Activating virtual environment...
CALL .\video\Scripts\activate.bat

:: --- Show menu ---
ECHO.
ECHO What do you want to start?
ECHO  1. Client
ECHO  2. Server
ECHO.

:: --- Get user choice ---
SET /P "CHOICE=Enter your choice (1 or 2): "

:: --- Run based on choice ---
IF "%CHOICE%"=="1" GOTO START_CLIENT
IF "%CHOICE%"=="2" GOTO START_SERVER

ECHO Invalid choice.
GOTO END

:START_CLIENT
ECHO Starting Client...
python client.py
GOTO END

:START_SERVER
ECHO Starting Server...
python server.py
GOTO END

:END
ECHO Script finished.
PAUSE
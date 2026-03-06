@echo off
REM Ductan Kids - School Email Fetcher
REM Maya (St. Cloud): Runs Wednesday via Task Scheduler
REM Isaac (SOCDS): Runs Friday via Task Scheduler
REM Downloads latest emails and logs results

cd /d "C:\Users\amosd\Downloads\Claude Code Sandbox\wednesday-folder"

echo ================================================ >> logs\weekly_fetch.log
echo %date% %time% - Starting fetch >> logs\weekly_fetch.log
echo ================================================ >> logs\weekly_fetch.log

echo --- Maya (St. Cloud Wednesday Folder) --- >> logs\weekly_fetch.log
C:\Python314\python.exe fetch_email.py >> logs\weekly_fetch.log 2>&1

echo --- Isaac (SOCDS Newsletter) --- >> logs\weekly_fetch.log
C:\Python314\python.exe fetch_socds.py >> logs\weekly_fetch.log 2>&1

echo Fetch completed with exit code %ERRORLEVEL% >> logs\weekly_fetch.log
echo. >> logs\weekly_fetch.log

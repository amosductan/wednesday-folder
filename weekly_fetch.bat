@echo off
REM Wednesday Folder Weekly Fetcher
REM Runs every Wednesday via Task Scheduler
REM Downloads latest PDF from Gmail and logs results

cd /d "C:\Users\amosd\Downloads\Claude Code Sandbox\wednesday-folder"

echo ================================================ >> logs\weekly_fetch.log
echo %date% %time% - Starting weekly fetch >> logs\weekly_fetch.log
echo ================================================ >> logs\weekly_fetch.log

C:\Python314\python.exe fetch_email.py >> logs\weekly_fetch.log 2>&1

echo Fetch completed with exit code %ERRORLEVEL% >> logs\weekly_fetch.log
echo. >> logs\weekly_fetch.log

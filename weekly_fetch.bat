@echo off
REM Ductan Kids - Weekly Auto Pipeline
REM Task Scheduler: Wed 4 PM (Maya) + Fri 4 PM (Isaac)
cd /d "C:\Users\amosd\Downloads\Claude Code Sandbox\wednesday-folder"
call "%USERPROFILE%\.secrets\load_env.cmd" "%CD%\.env" || exit /b 2
C:\Python314\python.exe weekly_pipeline.py

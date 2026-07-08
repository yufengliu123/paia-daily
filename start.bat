@echo off
cd /d "%~dp0"
start /min "" "C:\Users\28381\AppData\Local\Programs\Python\Python312\python.exe" server.py
timeout /t 3 /nobreak >nul
start http://localhost:8899


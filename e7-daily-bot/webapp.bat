@echo off
REM Launch the Streamlit webapp. Run this from the e7-daily-bot directory.
cd /d "%~dp0"
py -m streamlit run webapp\app.py

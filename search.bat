@echo off
cd /d "%~dp0"
py -m jra_scraper.cli.main %*

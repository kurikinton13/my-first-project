#!/data/data/com.termux/files/usr/bin/bash
cd ~/keiba
pip install -r requirements.txt
python web_app.py --host 0.0.0.0 --port 8080

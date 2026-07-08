"""
run.py — NetGuard AI launcher
Run this file: python run.py
"""
import sys
import os

# Force UTF-8 to prevent Windows encoding crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.environ['PYTHONIOENCODING'] = 'utf-8'

print("=" * 60)
print("  NetGuard AI - Multi-Agent Network Monitor")
print("  Dashboard : http://localhost:5000")
print("  Client    : http://localhost:5000/client")
print("=" * 60)

from app import app, bootstrap

# Bootstrap here — outside of the reloader's child process
bootstrap()

app.run(host="0.0.0.0", port=5000, threaded=True, debug=False, use_reloader=False)

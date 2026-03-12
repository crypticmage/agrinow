import os
import sys

# 1. Get the absolute path of the directory where this file sits
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Add 'src' to the system path so Python can find 'entry.py'
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

# 3. Bridge FastAPI (ASGI) to cPanel (WSGI)
from a2wsgi import ASGIMiddleware

try:
    # This matches your 'src/entry.py' and the 'app' object inside it
    from entry import app
    application = ASGIMiddleware(app)
except Exception as e:
    # This prints the EXACT error to your cPanel 'stderr.log'
    print(f"CRITICAL STARTUP ERROR: {e}")
    raise

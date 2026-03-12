import os
import sys

# 1. Add the 'src' directory to the Python path
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

# 2. Bridge: FastAPI (ASGI) -> cPanel (WSGI)
from a2wsgi import ASGIMiddleware
from entry import app  # This looks for 'app' inside 'src/entry.py'

# Passenger looks for the object named 'application'
application = ASGIMiddleware(app)

import os
import sys

# 1. Add the 'src' directory to the Python path so it can find 'entry.py'
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

# 2. Bridge: Use a2wsgi to convert FastAPI (ASGI) to cPanel (WSGI)
from a2wsgi import ASGIMiddleware

# 3. Import the 'app' object from entry.py inside the src folder
from entry import app

# Passenger looks for the object named 'application'
application = ASGIMiddleware(app)

import os
import sys

# 1. Add 'src' directory to path
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

# 2. Import bridge and app
from a2wsgi import ASGIMiddleware
from entry import app  # This imports the 'app' from 'src/entry.py'

# 3. Passenger expects 'application'
application = ASGIMiddleware(app)

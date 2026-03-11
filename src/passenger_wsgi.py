import sys, os

# Add your project directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Import the adapter
from a2wsgi import ASGIMiddleware

# IMPORTANT: We import 'app' from your 'entry.py' file
from entry import app 

# This is what cPanel looks for based on your 'Entry point' setting
application = ASGIMiddleware(app)
import sys
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)

log_file = os.path.join(base_dir, "passenger_error.log")

def log_msg(msg):
    try:
        with open(log_file, "a", encoding='utf-8') as f:
            import datetime
            f.write(f"[{datetime.datetime.now()}] {msg}\n")
    except:
        pass

log_msg("=== PASSENGER WSGI STARTUP ===")

try:
    from src.entry import app
    log_msg("[OK] FastAPI app imported")
    
    def application(environ, start_response):
        """WSGI application wrapper for FastAPI ASGI app"""
        import asyncio
        
        method = environ['REQUEST_METHOD']
        path = environ.get('PATH_INFO', '/')
        log_msg(f"[REQUEST] {method} {path}")
        
        try:
            # Build ASGI scope
            scope = {
                'type': 'http',
                'asgi': {'version': '3.0'},
                'http_version': '1.1',
                'method': method,
                'scheme': environ.get('wsgi.url_scheme', 'http'),
                'path': path,
                'query_string': environ.get('QUERY_STRING', '').encode(),
                'root_path': environ.get('SCRIPT_NAME', ''),
                'headers': [],
                'server': (environ.get('SERVER_NAME', 'localhost'), int(environ.get('SERVER_PORT', 80))),
                'client': (environ.get('REMOTE_ADDR', '127.0.0.1'), int(environ.get('REMOTE_PORT', 0)) or None),
            }
            
         
            status_code = 200
            response_headers = []
            body_parts = []
            
            async def receive():
                return {'type': 'http.request', 'body': b''}
            
            async def send(message):
                nonlocal status_code, response_headers, body_parts
                
                if message['type'] == 'http.response.start':
                    status_code = message['status']
                    response_headers = message.get('headers', [])
                    
                elif message['type'] == 'http.response.body':
                    body = message.get('body', b'')
                    if body:
                        body_parts.append(body)
            
            async def run_app():
                await app(scope, receive, send)
            
            # Run the ASGI app
            asyncio.run(run_app())
            
            
            headers = [(name.decode() if isinstance(name, bytes) else name,
                       value.decode() if isinstance(value, bytes) else value)
                      for name, value in response_headers]
            
            
            start_response(f"{status_code} OK", headers)
            
            log_msg(f"[RESPONSE] {method} {path} - {status_code}")
            
            
            return body_parts if body_parts else [b'']
            
        except Exception as e:
            log_msg(f"[ERROR] {type(e).__name__}: {str(e)}")
            import traceback
            log_msg(traceback.format_exc())
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [b'Internal Server Error']
    
    log_msg("[OK] WSGI application ready")
    
except Exception as e:
    log_msg(f"[CRITICAL] {type(e).__name__}: {str(e)}")
    import traceback
    log_msg(traceback.format_exc())
    raise

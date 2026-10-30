import sys
import os
import io
import base64
import urllib.parse

# Add repository root to Python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    import aws_wsgi
    USE_AWS_WSGI = True
except ImportError:
    USE_AWS_WSGI = False

from app import app

def wsgi_handler(event, context):
    if USE_AWS_WSGI:
        return aws_wsgi.handle_request(app, event, context)

    # Pure Python WSGI Gateway for Netlify Functions
    headers = event.get('headers') or {}
    method = event.get('httpMethod', 'GET').upper()
    
    # Extract path from Netlify headers or event
    path = (
        headers.get('x-nf-original-pathname') or
        headers.get('x-forwarded-uri') or
        event.get('path', '/')
    )
    if path.startswith('/.netlify/functions/api'):
        path = path[len('/.netlify/functions/api'):] or '/'

    query_params = event.get('queryStringParameters') or {}
    query_string = urllib.parse.urlencode(query_params)
    body = event.get('body') or ''
    if event.get('isBase64Encoded', False):
        try:
            body_bytes = base64.b64decode(body)
        except Exception:
            body_bytes = body.encode('utf-8')
    else:
        body_bytes = body.encode('utf-8') if isinstance(body, str) else (body or b'')

    environ = {
        'REQUEST_METHOD': method,
        'SCRIPT_NAME': '',
        'PATH_INFO': path,
        'QUERY_STRING': query_string,
        'SERVER_NAME': headers.get('host', 'localhost'),
        'SERVER_PORT': headers.get('x-forwarded-port', '443'),
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': headers.get('x-forwarded-proto', 'https'),
        'wsgi.input': io.BytesIO(body_bytes),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'CONTENT_LENGTH': str(len(body_bytes)),
        'CONTENT_TYPE': headers.get('content-type', headers.get('Content-Type', ''))
    }

    for k, v in headers.items():
        clean_key = k.upper().replace('-', '_')
        if clean_key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            environ[f"HTTP_{clean_key}"] = str(v)

    status_code = [200]
    response_headers = []

    def start_response(status, headers_list, exc_info=None):
        try:
            status_code[0] = int(status.split(' ')[0])
        except Exception:
            status_code[0] = 200
        response_headers.extend(headers_list)

    response_chunks = app(environ, start_response)
    response_body = b''.join(response_chunks)

    is_b64 = False
    try:
        body_text = response_body.decode('utf-8')
    except UnicodeDecodeError:
        body_text = base64.b64encode(response_body).decode('ascii')
        is_b64 = True

    res_headers = {}
    multi_headers = {}
    for k, v in response_headers:
        res_headers[k] = v
        multi_headers.setdefault(k, []).append(v)

    return {
        'statusCode': status_code[0],
        'headers': res_headers,
        'multiValueHeaders': multi_headers,
        'body': body_text,
        'isBase64Encoded': is_b64
    }

def handler(event, context):
    return wsgi_handler(event, context)

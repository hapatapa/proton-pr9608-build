#!/usr/bin/env python3
"""Xbox Live OAuth helper for Wine/Proton games.
Intercepts OAuth callback by redirecting to a local HTTP server.
Usage: python3 oauth_helper.py <login_url> <output_file>
"""
import sys
import os
import webbrowser
import http.server
import urllib.parse
import time

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    callback_data = None

    def do_GET(self):
        OAuthHandler.callback_data = self.path
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(
            b'<html><body style="text-align:center;margin-top:100px;'
            b'font-family:sans-serif">'
            b'<h2>Login successful!</h2>'
            b'<p>You can close this tab and return to the game.</p>'
            b'</body></html>'
        )

    def log_message(self, format, *args):
        pass

def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    login_url = sys.argv[1]
    output_file = sys.argv[2]

    server = http.server.HTTPServer(('127.0.0.1', 0), OAuthHandler)
    port = server.server_address[1]

    parsed = urllib.parse.urlparse(login_url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    params['redirect_uri'] = ['http://127.0.0.1:{}/'.format(port)]
    new_url = urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(params, doseq=True))
    )

    webbrowser.open(new_url)

    server.timeout = 0.5
    deadline = time.time() + 300
    while time.time() < deadline:
        server.handle_request()
        if OAuthHandler.callback_data is not None:
            break

    server.server_close()

    if OAuthHandler.callback_data:
        with open(output_file, 'w') as f:
            f.write(OAuthHandler.callback_data)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
"""Real loopback HTTPS source and deliberately hung HTTP origin."""
import functools,http.server,json,socket,ssl,threading,time
from pathlib import Path
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        with Path('evidence/mvpfix/wp16/origin.jsonl').open('a') as f: f.write(json.dumps(dict(time=time.time(),user_agent=self.headers.get('User-Agent'),route='missing' if 'not-present' in self.path else 'html' if 'html' in self.path else 'media'))+'\n')
        super().do_GET()
def hang():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); listener.bind(('127.0.0.1',17878)); listener.listen()
        held=[]
        while True: held.append(listener.accept()[0])
threading.Thread(target=hang,daemon=True).start()
server=http.server.ThreadingHTTPServer(('127.0.0.1',17877),functools.partial(Handler,directory='.wp16runtime/media'))
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain('.wp16runtime/cert.pem','.wp16runtime/key.pem')
server.socket=ctx.wrap_socket(server.socket,server_side=True); server.serve_forever()

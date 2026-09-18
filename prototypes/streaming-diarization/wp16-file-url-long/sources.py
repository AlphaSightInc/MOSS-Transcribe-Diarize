"""Real loopback HTTPS source and deliberately hung HTTP origin."""
import argparse,functools,http.server,json,socket,ssl,threading,time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--scratch',type=Path,default=Path('.wp16runtime'))
parser.add_argument('--out',type=Path,default=Path('evidence/mvpfix/wp16'))
parser.add_argument('--source-port',type=int,default=17877)
parser.add_argument('--hang-port',type=int,default=17878)
parser.add_argument('--cert',type=Path,default=Path('.wp16runtime/cert.pem'))
parser.add_argument('--key',type=Path,default=Path('.wp16runtime/key.pem'))
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        with (args.out/'origin.jsonl').open('a') as f: f.write(json.dumps(dict(time=time.time(),user_agent=self.headers.get('User-Agent'),route='missing' if 'not-present' in self.path else 'html' if 'html' in self.path else 'media'))+'\n')
        super().do_GET()
def hang():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); listener.bind(('127.0.0.1',args.hang_port)); listener.listen()
        held=[]
        while True: held.append(listener.accept()[0])
threading.Thread(target=hang,daemon=True).start()
server=http.server.ThreadingHTTPServer(('127.0.0.1',args.source_port),functools.partial(Handler,directory=str(args.scratch/'media')))
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(args.cert,args.key)
server.socket=ctx.wrap_socket(server.socket,server_side=True); server.serve_forever()

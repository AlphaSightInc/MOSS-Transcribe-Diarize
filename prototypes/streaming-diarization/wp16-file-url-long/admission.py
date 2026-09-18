"""Header-only control isolates server capacity refusal; NOT browser file proof."""
import httpx,json,shutil,socket,ssl
from pathlib import Path
base='https://127.0.0.1:17876'; ctx=ssl.create_default_context(cafile='.wp16runtime/ca.pem')
with httpx.Client(base_url=base,verify=ctx) as client:
 client.post('/api/workspace/bootstrap').raise_for_status()
 before=len(client.get('/api/meetings').json()['meetings']); free=shutil.disk_usage('.wp16runtime/state/file-work').free; length=(free-512*1024*1024)//2+1048576
 cookie='; '.join(f'{k}={v}' for k,v in client.cookies.items())
 with ctx.wrap_socket(socket.create_connection(('127.0.0.1',17876),timeout=10),server_hostname='127.0.0.1') as connection:
  connection.sendall(f'POST /api/meetings/file HTTP/1.1\r\nHost: 127.0.0.1:17876\r\nCookie: {cookie}\r\nContent-Length: {length}\r\nContent-Type: multipart/form-data; boundary=wp16\r\nConnection: close\r\n\r\n'.encode())
  raw=b''
  while chunk:=connection.recv(8192): raw+=chunk
 response=raw.decode(); row=dict(control='headers only, zero body bytes sent',declared_bytes=length,free_bytes=free,status=response.splitlines()[0],body=response.split('\r\n\r\n')[1],meetings_before=before,meetings_after=len(client.get('/api/meetings').json()['meetings']))
Path('evidence/mvpfix/wp16/admission-control.json').write_text(json.dumps(row,indent=2)+'\n'); print(json.dumps(row))

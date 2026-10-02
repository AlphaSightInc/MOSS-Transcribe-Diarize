"""Playwright acquires the page, then disconnects its Network observer for native memory measurement."""
import json, subprocess, time
from urllib.request import urlopen
from websockets.sync.client import connect
from playwright.sync_api import sync_playwright

class CDP:
    def __init__(self,url):self.ws=connect(url,max_size=100000000);self.sequence=0;self.events=[]
    def send(self,method,params=None):
        self.sequence+=1;self.ws.send(json.dumps({'id':self.sequence,'method':method,'params':params or {}}))
        while True:
            reply=json.loads(self.ws.recv(timeout=60))
            if reply.get('id')!=self.sequence:
                if reply.get('method','').startswith('Tracing.'):self.events.append(reply)
                continue
            if 'error' in reply:raise RuntimeError(reply['error'])
            return reply.get('result',{})
    def evaluate(self,expression,arg=None):
        js=expression if arg is None else f'({expression})({json.dumps(arg)})'
        r=self.send('Runtime.evaluate',{'expression':js,'awaitPromise':True,'returnByValue':True})
        if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')

class Chrome:
    def __init__(self,state,port,url):
        self.process=subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-extensions','--disable-sync','--use-mock-keychain','--password-store=basic',f'--remote-debugging-port={port}',f'--user-data-dir={state / "chrome-profile"}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        endpoint=f'http://127.0.0.1:{port}';deadline=time.monotonic()+15
        while True:
            try:
                with urlopen(endpoint+'/json/version',timeout=.5) as r:version=json.load(r)
                break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp(endpoint);page=browser.contexts[0].pages[0]
            page.goto(url);page.wait_for_function('typeof run === "function"');browser.close() # external Chrome stays alive
        with urlopen(endpoint+'/json/list') as r:targets=json.load(r)
        target=next(x for x in targets if x['type']=='page')
        self.page=CDP(target['webSocketDebuggerUrl']);self.browser=CDP(version['webSocketDebuggerUrl']);self.version=version['Browser']
        self.page.send('Tracing.start',{'categories':'devtools.timeline','transferMode':'ReportEvents'})
        self.page.evaluate('console.timeStamp("p74-renderer")')
        self.page.send('Tracing.end')
        while not any(x.get('method')=='Tracing.tracingComplete' for x in self.page.events):
            self.page.events.append(json.loads(self.page.ws.recv(timeout=10)))
        events=[e for x in self.page.events if x.get('method')=='Tracing.dataCollected' for e in x['params']['value']]
        self.renderer_pid=next(e['pid'] for e in events if e.get('name')=='TimeStamp' and e.get('args',{}).get('data',{}).get('message')=='p74-renderer')
        self.page.events.clear()
    def close(self):
        self.page.ws.close();self.browser.ws.close();self.process.terminate();self.process.wait(timeout=15)

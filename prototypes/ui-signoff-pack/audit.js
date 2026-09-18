() => {
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);for(let a=e;a;a=a.parentElement){const t=getComputedStyle(a);if(t.clip!=='auto'||t.clipPath!=='none'||Number(t.opacity)===0)return false;}return r.width>1&&r.height>1&&s.visibility==='visible'&&s.display!=='none'&&!e.closest('[hidden]')};
  const label=e=>e.getAttribute('aria-label')||e.getAttribute('title')||(e.labels?[...e.labels].map(x=>x.innerText).join(' '):'')||e.innerText||e.getAttribute('placeholder')||'';
  const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d');
  const rgba=s=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=s;ctx.fillRect(0,0,1,1);const c=[...ctx.getImageData(0,0,1,1).data];c[3]/=255;return c};
  const over=(f,b)=>{const a=f[3]+b[3]*(1-f[3]);return [0,1,2].map(i=>(f[i]*f[3]+b[i]*b[3]*(1-f[3]))/a).concat(a)};
  const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
  const contrast=[], clipping=[], focus=[], controls=[];
  for(const e of document.querySelectorAll('body *')) {
    if(!visible(e))continue;
    const s=getComputedStyle(e), r=e.getBoundingClientRect();
    if(e.matches('button,a[href],input,textarea,select,[tabindex]')){
      controls.push({tag:e.tagName,role:e.getAttribute('role'),name:label(e).trim(),disabled:!!e.disabled});
      if(!e.disabled&&e.tabIndex>=0)focus.push({tag:e.tagName,name:label(e).trim(),tabIndex:e.tabIndex,x:Math.round(r.x),y:Math.round(r.y)});
    }
    const own=[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    if(own && e.clientWidth>0 && e.scrollWidth>e.clientWidth+1 && !['auto','scroll'].includes(s.overflowX))clipping.push({tag:e.tagName,class:e.className,text:own.slice(0,120),overflow:s.overflowX,ellipsis:s.textOverflow==='ellipsis',client:e.clientWidth,scroll:e.scrollWidth});
    if(!own||e.closest('button:disabled,fieldset:disabled')||e.disabled)continue;
    let bg=[255,255,255,1],unknown=false;const ancestors=[];
    for(let a=e;a;a=a.parentElement)ancestors.unshift(a);
    for(const a of ancestors){const as=getComputedStyle(a); const c=rgba(as.backgroundColor);if(c){bg=over(c,bg);if(c[3]===1)unknown=false;}if(as.backgroundImage!=='none')unknown=true;if(Number(as.opacity)!==1)unknown=true;}
    const fg=rgba(s.color);if(!fg)continue;const f=over(fg,bg);const ratio=(Math.max(lum(f),lum(bg))+.05)/(Math.min(lum(f),lum(bg))+.05);
    const large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&Number(s.fontWeight)>=700);const bar=large?3:4.5;
    contrast.push({text:own.slice(0,140),tag:e.tagName,class:typeof e.className==='string'?e.className:'',color:s.color,background:bg.slice(0,3),fontSize:s.fontSize,ratio:+ratio.toFixed(2),required:bar,result:unknown?'manual-review-gradient-or-opacity':ratio>=bar?'pass':'fail'});
  }
  const text=[];
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode,e=node.parentElement,value=node.textContent.trim();
    if(value&&e&&!e.closest('script,style,select')&&visible(e))text.push(value);
  }
  for(const e of document.querySelectorAll('select'))if(visible(e))text.push(e.selectedOptions[0]?.textContent||'');
  const overlaps=[];
  for(const [left,right] of [['.top-status','.session-meta'],['.control-panel','.transcript-shell'],['.top-status','.transcript-shell']]){
    const a=document.querySelector(left)?.getBoundingClientRect(),b=document.querySelector(right)?.getBoundingClientRect();
    if(a&&b&&Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)overlaps.push({left,right});
  }
  return {geometric_overlaps:overlaps,transcript_rows:[...document.querySelectorAll('.utt')].map(e=>({state:e.dataset.state,lane:e.querySelector('.utt-lane')?.textContent,text:e.querySelector('.utt-text')?.textContent})),visible_copy:text.join('\n'),copy_scope:'Rendered text excluding CSS-clipped headings and unselected options; includes content reachable by scrolling panels',horizontal_scroll:document.documentElement.scrollWidth>innerWidth,document_width:document.documentElement.scrollWidth,viewport_width:innerWidth,clipping,contrast,controls,focus_order:focus,focus_anomalies:focus.filter(x=>x.tabIndex>0),active_focus:label(document.activeElement),overlap_review:'Requires screenshot review; intentional transcript time overlap is not geometric overlap.'};
}

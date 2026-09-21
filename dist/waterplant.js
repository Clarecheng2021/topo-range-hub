const NS='http://www.w3.org/2000/svg';
const $=id=>document.getElementById(id);
const typeLabels={internet:'互联网',firewall:'防火墙',router:'路由/行为管理',switch:'交换机',server:'服务器',workstation:'工作站',hmi:'HMI',plc:'PLC',camera:'摄像机',security:'安防终端',display:'显示终端',sensor:'现场设备'};
const typeIcons={internet:'NET',firewall:'FW',router:'RTR',switch:'SW',server:'SRV',workstation:'PC',hmi:'HMI',plc:'PLC',camera:'CAM',security:'SEC',display:'LCD',sensor:'I/O'};
const zoneColors={enterprise:'#5aa9ff',dmz:'#ffb15a',security:'#ff6b8a',control:'#9c7cff',field:'#35d6b2'};
const profiles={internet:'linux-host',firewall:'generic-firewall',router:'frr-router',switch:'l2-switch',server:'linux-host',workstation:'linux-host',hmi:'hmi-web',plc:'profinet-plc',camera:'camera-rtsp',security:'linux-host',display:'linux-host',sensor:'field-simulator'};
let zoneDefs=[];
let nodes=[],links=[],selectedId=null,generated='',linkMode=false,linkSource=null,dragging=null,dragMoved=false;
let linkTarget=null;
let currentView={x:0,y:0,w:1400,h:820};

function svgEl(tag,attrs={}){const el=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el}
function clipped(s,n=12){return s.length>n?s.slice(0,n-1)+'…':s}
function zoneName(id){return zoneDefs.find(z=>z.id===id)?.name||id}
function nodeCenter(n){return{x:n.x+55,y:n.y+24}}
function applyView(){ $('topologyCanvas').setAttribute('viewBox',`${currentView.x} ${currentView.y} ${currentView.w} ${currentView.h}`) }

function render(){
 updateConnectionUI();
 const legend=$('zoneLegend');legend.hidden=!zoneDefs.length;legend.replaceChildren(...zoneDefs.map(z=>{const entry=document.createElement('span');const dot=document.createElement('i');dot.className='dot';dot.style.background=zoneColors[z.id]||'#35d6b2';entry.append(dot,document.createTextNode(z.name));return entry}));
 const svg=$('topologyCanvas');svg.innerHTML='';applyView();
 zoneDefs.forEach(z=>{const r=svgEl('rect',{x:z.x,y:z.y,width:z.w,height:z.h,fill:zoneColors[z.id]+'0A',stroke:zoneColors[z.id]+'66',class:'zone-bg'});svg.append(r);const t=svgEl('text',{x:z.x+14,y:z.y+24,fill:zoneColors[z.id],class:'zone-title'});t.textContent=z.name;svg.append(t)});
 links.forEach(l=>{const a=nodes.find(n=>n.id===l[0]),b=nodes.find(n=>n.id===l[1]);if(!a||!b)return;const ac=nodeCenter(a),bc=nodeCenter(b),mx=(ac.x+bc.x)/2;const p=svgEl('path',{d:`M ${ac.x} ${ac.y} C ${mx} ${ac.y}, ${mx} ${bc.y}, ${bc.x} ${bc.y}`,class:'link '+(a.id===selectedId||b.id===selectedId?'active':'')});svg.append(p);if(l[2]&&Math.hypot(ac.x-bc.x,ac.y-bc.y)>150){const t=svgEl('text',{x:mx+4,y:(ac.y+bc.y)/2-5,class:'link-label'});t.textContent=l[2];svg.append(t)}});
 nodes.forEach(n=>{const g=svgEl('g',{class:`node ${n.id===selectedId?'selected':''} ${n.id===linkSource?'link-source':''}`,transform:`translate(${n.x} ${n.y})`,'data-id':n.id,tabindex:'0',role:'button','aria-label':`${n.name} ${n.ip}`});const rect=svgEl('rect',{width:110,height:48,rx:8,fill:'#101f2a',stroke:zoneColors[n.zone]});const icon=svgEl('text',{x:10,y:20,class:'node-icon'});icon.textContent=typeIcons[n.type];const title=svgEl('text',{x:39,y:19,class:'node-title'});title.textContent=clipped(n.name);const meta=svgEl('text',{x:39,y:35,class:'node-meta'});meta.textContent=n.ip||'待分配 IP';const dot=svgEl('circle',{cx:102,cy:8,r:3,class:`confidence-ring ${n.confidence<.85?'low':''}`});g.append(rect,icon,title,meta,dot);g.addEventListener('pointerdown',e=>startDrag(e,n.id));g.addEventListener('click',e=>handleNodeClick(e,n.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();handleNodeClick(e,n.id)}});svg.append(g)});
 svg.querySelectorAll('.node').forEach(g=>g.classList.toggle('link-target',linkMode&&g.getAttribute('data-id')===linkTarget));
 $('nodeCount').textContent=nodes.length;$('linkCount').textContent=links.length;$('zoneCount').textContent=zoneDefs.length;$('issueCount').textContent=nodes.filter(n=>n.confidence<.85).length;renderSummary();
 window.onTopologyChanged?.();
}

function renderSummary(){const counts={};nodes.forEach(n=>counts[n.type]=(counts[n.type]||0)+1);$('typeSummary').innerHTML=Object.entries(counts).map(([k,v])=>`<span>${typeLabels[k]} ${v}</span>`).join('')}
function selectNode(id){selectedId=id;const n=nodes.find(x=>x.id===id);if(!n)return;$('nodeName').value=n.name;$('nodeType').value=n.type;$('nodeIp').value=n.ip;$('nodeZone').value=n.zone;$('nodeProfile').value=n.profile;$('confidence').textContent=Math.round(n.confidence*100)+'%';$('findingText').textContent=n.confidence<.85?'文字或设备型号不完全清晰，已按区域位置和相邻设备推断，请人工确认':'设备图标、中文标签、所属区域和线路走向联合识别';render()}
function syncForm(){const n=nodes.find(x=>x.id===selectedId);if(!n)return;n.name=$('nodeName').value;n.type=$('nodeType').value;n.ip=$('nodeIp').value;n.zone=$('nodeZone').value;n.profile=$('nodeProfile').value;n.confidence=1;render()}
function canvasPoint(e){const r=$('topologyCanvas').getBoundingClientRect();return{x:currentView.x+(e.clientX-r.left)*currentView.w/r.width,y:currentView.y+(e.clientY-r.top)*currentView.h/r.height}}
function startDrag(e,id){if(linkMode)return;const n=nodes.find(x=>x.id===id),p=canvasPoint(e);dragging={id,dx:p.x-n.x,dy:p.y-n.y,startX:e.clientX,startY:e.clientY};dragMoved=false;selectedId=id;e.preventDefault()}
window.addEventListener('pointermove',e=>{if(!dragging)return;if(!dragMoved&&Math.hypot(e.clientX-dragging.startX,e.clientY-dragging.startY)<5)return;const n=nodes.find(x=>x.id===dragging.id),p=canvasPoint(e);if(!n)return;n.x=Math.max(5,Math.min(1285,p.x-dragging.dx));n.y=Math.max(5,Math.min(767,p.y-dragging.dy));dragMoved=true;render()});
window.addEventListener('pointerup',()=>{dragging=null});
function connectionIssue(){
 if(!nodes.some(n=>n.id===linkSource))return '请选择起点设备';
 if(!nodes.some(n=>n.id===linkTarget))return '请选择终点设备';
 if(linkSource===linkTarget)return '起点和终点不能是同一台设备';
 if(links.some(l=>(l[0]===linkSource&&l[1]===linkTarget)||(l[1]===linkSource&&l[0]===linkTarget)))return '这两台设备已存在连接，请选择其他设备';
 return '';
}
function updateConnectionUI(){
 if(linkMode&&((linkSource&&!nodes.some(n=>n.id===linkSource))||(linkTarget&&!nodes.some(n=>n.id===linkTarget)))){linkMode=false;linkSource=null;linkTarget=null}
 $('connectionPanel').hidden=!linkMode;
 $('linkNode').textContent=linkMode?'取消连接':'连接设备';
 $('linkNode').setAttribute('aria-pressed',String(linkMode));
 $('linkNode').disabled=nodes.length<2;
 $('canvasWrap').classList.toggle('connecting',linkMode);
 if(!linkMode)return;
 for(const [field,value] of [['connectionSource',linkSource],['connectionTarget',linkTarget]]){
  const select=$(field);const blank=document.createElement('option');blank.value='';blank.textContent='请选择设备';
  select.replaceChildren(blank,...nodes.map(n=>{const option=document.createElement('option');option.value=n.id;option.textContent=n.name;return option}));select.value=value||'';
 }
 const issue=connectionIssue();$('confirmConnection').disabled=Boolean(issue);
 $('connectionHint').textContent=issue||`${nodes.find(n=>n.id===linkSource).name} → ${nodes.find(n=>n.id===linkTarget).name}，点击“确认连接”创建链路`;
}
function beginConnection(){
 if(nodes.length<2){toast('至少需要两台设备才能连接');return}
 linkMode=true;linkSource=nodes.some(n=>n.id===selectedId)?selectedId:null;linkTarget=null;dragging=null;dragMoved=false;render();
 toast(linkSource?'已将当前设备设为起点，请选择终点':'请选择起点和终点设备');
}
function cancelConnection(){linkMode=false;linkSource=null;linkTarget=null;dragMoved=false;render()}
function confirmConnection(){
 const issue=connectionIssue();if(!linkMode||issue){if(issue)toast(issue);return}
 const source=linkSource,target=linkTarget;
 links.push([source,target,'ethernet']);generated='';$('outputPanel').hidden=true;$('downloadBtn').disabled=true;
 cancelConnection();selectNode(target);toast('链路已创建');
}
function handleNodeClick(e,id){
 if(linkMode){if(!linkSource)linkSource=id;else linkTarget=id;dragMoved=false;render();return}
 if(dragMoved){dragMoved=false;selectNode(id);return}selectNode(id);
}

function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');clearTimeout(toast.t);toast.t=setTimeout(()=>el.classList.remove('show'),2600)}
function topologyIR(){return{name:'toporangehub-topology',title:'TopoRangeHub 可编辑矢量拓扑',version:'0.3',source:{kind:'canvas',image_size:{width:1320,height:760}},isolation:{production_bridge:false,internet_egress:false},zones:zoneDefs.map(({x,y,w,h,...z})=>({...z,bbox:{x,y,width:w,height:h}})),nodes:nodes.map(n=>({...n,position:{x:n.x,y:n.y}})),links:links.map((l,i)=>({id:`link-${i+1}`,source:l[0],target:l[1],protocol:l[2]||'ethernet'}))}}
function generate(){
 generated=JSON.stringify(topologyIR(),null,2);
 $('outputCode').textContent=generated;$('outputPanel').hidden=false;$('downloadBtn').disabled=false;
 $('deployRangeBtn').disabled=nodes.length===0;
 document.querySelectorAll('.workflow-step')[2].classList.add('active');
 $('runState').textContent=$('orchestrator').value==='docker-range'?'部署预览已生成，人工确认后可启动隔离靶场':'通用矢量拓扑 JSON 已生成';
 $('outputPanel').scrollIntoView({behavior:'smooth',block:'start'});toast(`已整理 ${nodes.length} 台设备和 ${links.length} 条链路`)
}
function deployRange(){
 if(!nodes.length){toast('请先导入并审核至少一台设备');return}
 if(!confirm('确认按当前审核后的拓扑启动隔离虚拟靶场？运行时不会桥接生产网络或开放互联网出口。'))return;
 const topology=topologyIR();topology.review={status:'approved',approved_at:new Date().toISOString(),method:'manual-ui-review'};
 const button=$('deployRangeBtn');button.disabled=true;button.textContent='正在启动…';
 fetch('/api/ranges/deploy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(topology)})
  .then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail||'靶场启动失败');return data})
  .then(data=>{$('runState').textContent=`隔离靶场已启动：${data.id}（${data.nodes.length} 台节点，${data.links.length} 条链路）`;toast('隔离虚拟靶场已启动')})
  .catch(error=>{button.disabled=false;$('runState').textContent='靶场启动失败：'+error.message;toast(error.message)})
  .finally(()=>{button.textContent='启动隔离靶场'})
}
function download(content,name,type='text/plain'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}

$('showOriginal').addEventListener('click',()=>{const original=$('uploadedImage').classList.toggle('original');$('showOriginal').textContent=original?'返回矢量拓扑':'显示原图'});
$('nodeForm').addEventListener('input',syncForm);$('nodeForm').addEventListener('change',syncForm);
$('addNode').addEventListener('click',()=>{const id=`asset-${Date.now()}`;nodes.push({id,name:'新增设备',type:'server',ip:'待分配',zone:'field',profile:'linux-host',x:870,y:735,confidence:1});selectedId=id;selectNode(id);toast('已添加设备，可拖动到目标位置')});
$('deleteNode').addEventListener('click',()=>{if(!selectedId)return;const n=nodes.find(x=>x.id===selectedId);nodes=nodes.filter(x=>x.id!==selectedId);links=links.filter(l=>!l.includes(selectedId));selectedId=nodes[0]?.id||null;if(selectedId)selectNode(selectedId);else render();toast(`已删除 ${n?.name||'设备'} 及关联链路`)});
$('linkNode').addEventListener('click',()=>linkMode?cancelConnection():beginConnection());
$('connectionSource').addEventListener('change',e=>{linkSource=e.target.value||null;render()});
$('connectionTarget').addEventListener('change',e=>{linkTarget=e.target.value||null;render()});
$('confirmConnection').addEventListener('click',confirmConnection);
$('cancelConnection').addEventListener('click',cancelConnection);
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&linkMode){e.preventDefault();cancelConnection();toast('已取消连接')}});
$('zoomIn').addEventListener('click',()=>{currentView={x:currentView.x+currentView.w*.1,y:currentView.y+currentView.h*.1,w:currentView.w*.8,h:currentView.h*.8};applyView()});
$('zoomOut').addEventListener('click',()=>{currentView={x:Math.max(0,currentView.x-currentView.w*.125),y:Math.max(0,currentView.y-currentView.h*.125),w:Math.min(1800,currentView.w*1.25),h:Math.min(1050,currentView.h*1.25)};applyView()});
$('fitView').addEventListener('click',()=>{currentView={x:0,y:0,w:1400,h:820};applyView()});
$('generateBtn').addEventListener('click',generate);$('deployRangeBtn').addEventListener('click',deployRange);$('downloadBtn').addEventListener('click',()=>download(generated,'toporangehub.topology.json','application/json'));
$('exportJson').addEventListener('click',()=>download(JSON.stringify(topologyIR(),null,2),'toporangehub.topology.json','application/json'));
$('copyBtn').addEventListener('click',async()=>{await navigator.clipboard.writeText(generated);toast('配置已复制')});
function resetForUpload(){
 linkMode=false;linkSource=null;linkTarget=null;dragging=null;dragMoved=false;
 nodes=[];links=[];zoneDefs=[];selectedId=null;generated='';
 $('nodeName').value='';$('nodeIp').value='';
 $('uploadedImage').removeAttribute('src');$('uploadedImage').style.display='none';
 $('exportJson').disabled=true;
 $('sourceHint').textContent='上传 PNG、JPEG 或 WebP 拓扑图后开始分析';
 $('runState').textContent='等待上传拓扑图';$('confidence').textContent='--';
 $('findingText').textContent='上传图片后，GLM 将识别区域、设备和可见连接关系。';
 render();
}
resetForUpload();

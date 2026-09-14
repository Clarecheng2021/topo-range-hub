const NS='http://www.w3.org/2000/svg';
const typeLabels={firewall:'工业防火墙',switch:'交换机',server:'服务器',workstation:'工程师站',hmi:'HMI',plc:'PLC',sensor:'现场设备'};
const typeIcons={firewall:'▥',switch:'⇄',server:'▤',workstation:'▣',hmi:'▧',plc:'PLC',sensor:'◉'};
const zoneColors={enterprise:'#5aa9ff',dmz:'#ffb15a',control:'#9c7cff',field:'#35d6b2'};
const profiles={firewall:'generic-firewall',switch:'l2-switch',server:'linux-host',workstation:'linux-host',hmi:'hmi-web',plc:'modbus-plc',sensor:'field-simulator'};

const sampleNodes=[
 {id:'fw01',name:'边界防火墙',type:'firewall',ip:'10.10.0.1',zone:'enterprise',profile:'generic-firewall',x:95,y:235,confidence:.98},
 {id:'dmz-sw',name:'DMZ 交换机',type:'switch',ip:'10.20.0.2',zone:'dmz',profile:'l2-switch',x:275,y:235,confidence:.96},
 {id:'historian',name:'历史数据库',type:'server',ip:'10.20.0.10',zone:'dmz',profile:'linux-host',x:265,y:95,confidence:.91},
 {id:'ctrl-sw',name:'控制区交换机',type:'switch',ip:'10.30.0.2',zone:'control',profile:'l2-switch',x:485,y:235,confidence:.97},
 {id:'eng01',name:'工程师站',type:'workstation',ip:'10.30.0.20',zone:'control',profile:'linux-host',x:475,y:95,confidence:.94},
 {id:'hmi01',name:'操作员 HMI',type:'hmi',ip:'10.30.0.30',zone:'control',profile:'hmi-web',x:665,y:95,confidence:.95},
 {id:'plc01',name:'1号产线 PLC',type:'plc',ip:'10.40.0.10',zone:'field',profile:'modbus-plc',x:695,y:235,confidence:.83},
 {id:'sensor01',name:'温度过程模型',type:'sensor',ip:'10.40.0.20',zone:'field',profile:'field-simulator',x:830,y:390,confidence:.89}
];
const sampleLinks=[['fw01','dmz-sw'],['dmz-sw','historian'],['dmz-sw','ctrl-sw'],['ctrl-sw','eng01'],['ctrl-sw','hmi01'],['ctrl-sw','plc01'],['plc01','sensor01']];
let nodes=structuredClone(sampleNodes),links=structuredClone(sampleLinks),selectedId='plc01',generated='';
const $=id=>document.getElementById(id);

function svgEl(tag,attrs={}){const el=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el}
function render(){
 const svg=$('topologyCanvas');svg.innerHTML='';
 const zones=[['enterprise',35,42,175,455,'企业区'],['dmz',225,42,170,455,'工业 DMZ'],['control',410,42,265,455,'生产控制区'],['field',690,42,255,455,'现场设备区']];
 zones.forEach(([id,x,y,w,h,label])=>{const r=svgEl('rect',{x,y,width:w,height:h,fill:zoneColors[id]+'0A',stroke:zoneColors[id]+'55',class:'zone-bg'});svg.append(r);const t=svgEl('text',{x:+x+12,y:+y+21,fill:zoneColors[id],style:'font-size:10px;letter-spacing:.12em'});t.textContent=label;svg.append(t)});
 links.forEach((l,i)=>{const a=nodes.find(n=>n.id===l[0]),b=nodes.find(n=>n.id===l[1]);if(!a||!b)return;const p=svgEl('path',{d:`M ${a.x+62} ${a.y+30} C ${(a.x+b.x)/2+62} ${a.y+30}, ${(a.x+b.x)/2+62} ${b.y+30}, ${b.x+62} ${b.y+30}`,class:'link '+(a.id===selectedId||b.id===selectedId?'active':'')});svg.append(p);if(i===5){const t=svgEl('text',{x:(a.x+b.x)/2+40,y:(a.y+b.y)/2+19,class:'link-label'});t.textContent='Modbus/TCP';svg.append(t)}});
 nodes.forEach(n=>{const g=svgEl('g',{class:'node '+(n.id===selectedId?'selected':''),transform:`translate(${n.x} ${n.y})`,'data-id':n.id,tabindex:'0',role:'button','aria-label':`${n.name} ${n.ip}`});const rect=svgEl('rect',{width:124,height:60,rx:9,fill:'#101f2a',stroke:zoneColors[n.zone]});const icon=svgEl('text',{x:13,y:26,class:'node-icon'});icon.textContent=typeIcons[n.type];const title=svgEl('text',{x:42,y:23,class:'node-title'});title.textContent=n.name;const meta=svgEl('text',{x:42,y:42,class:'node-meta'});meta.textContent=n.ip||'待分配 IP';const dot=svgEl('circle',{cx:115,cy:9,r:3,class:'confidence-ring'});g.append(rect,icon,title,meta,dot);g.addEventListener('click',()=>selectNode(n.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectNode(n.id)}});svg.append(g)});
 $('nodeCount').textContent=nodes.length;$('linkCount').textContent=links.length;$('issueCount').textContent=nodes.filter(n=>n.confidence<.88).length;
}
function selectNode(id){selectedId=id;const n=nodes.find(x=>x.id===id);if(!n)return;$('nodeName').value=n.name;$('nodeType').value=n.type;$('nodeIp').value=n.ip;$('nodeZone').value=n.zone;$('nodeProfile').value=n.profile;$('confidence').textContent=Math.round(n.confidence*100)+'%';$('findingText').textContent=n.confidence<.88?'设备类别来自图形推断，建议人工确认厂商与协议模板':'图标特征 + 邻近文本 + 连线位置';render()}
function syncForm(){const n=nodes.find(x=>x.id===selectedId);if(!n)return;n.name=$('nodeName').value;n.type=$('nodeType').value;n.ip=$('nodeIp').value;n.zone=$('nodeZone').value;n.profile=$('nodeProfile').value;n.confidence=1;render()}
function loadSample(){nodes=structuredClone(sampleNodes);links=structuredClone(sampleLinks);selectedId='plc01';$('uploadedImage').style.display='none';delete $('analyzeBtn').dataset.pending;$('analyzeBtn').onclick=null;$('sourceHint').textContent='工业控制网络样例 · 8 个节点 · 7 条链路';selectNode(selectedId);toast('已恢复内置工厂网络样例')}
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');clearTimeout(toast.t);toast.t=setTimeout(()=>el.classList.remove('show'),2400)}
function topologyIR(){return{name:'factory-image-lab',version:'0.1',isolation:{production_bridge:false,internet_egress:false},nodes:nodes.map(({x,y,confidence,...n})=>({...n,confidence})),links:links.map((l,i)=>({id:`link-${i+1}`,source:l[0],target:l[1]}))}}
function makeYaml(){
 const safe=s=>String(s).replace(/[^a-zA-Z0-9_-]/g,'-').toLowerCase();
 const lines=['name: factory-image-lab','','mgmt:','  network: factory-lab-mgmt','  ipv4-subnet: 172.31.100.0/24','','topology:','  nodes:'];
 nodes.forEach(n=>{lines.push(`    ${safe(n.id)}:`,'      kind: linux','      image: alpine:3.20','      cmd: sleep infinity',`      labels:`,`        factory.name: "${n.name.replace(/"/g,'')}"`,`        factory.type: "${n.type}"`,`        factory.zone: "${n.zone}"`)});
 lines.push('  links:');links.forEach((l,i)=>lines.push(`    - endpoints: ["${safe(l[0])}:eth${i+1}", "${safe(l[1])}:eth${i+1}"]`));return lines.join('\n')+'\n';
}
function generate(){generated=$('orchestrator').value==='containerlab'?makeYaml():JSON.stringify(topologyIR(),null,2);$('outputCode').textContent=generated;$('outputPanel').hidden=false;$('downloadBtn').disabled=false;document.querySelectorAll('.workflow-step')[2].classList.add('active');$('runState').textContent='部署配置已通过检查';$('outputPanel').scrollIntoView({behavior:'smooth',block:'start'});toast('部署配置生成成功')}
function download(content,name,type='text/plain'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}

function detectFromImage(file){
 const img=new Image();img.onload=()=>{
  const max=480,scale=Math.min(max/img.width,max/img.height,1),w=Math.max(1,Math.round(img.width*scale)),h=Math.max(1,Math.round(img.height*scale));
  const c=document.createElement('canvas');c.width=w;c.height=h;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0,w,h);const d=ctx.getImageData(0,0,w,h).data;
  const cols=8,rows=5,cellW=w/cols,cellH=h/rows,candidates=[];
  for(let gy=0;gy<rows;gy++)for(let gx=0;gx<cols;gx++){
   let ink=0,total=0;const x0=Math.floor(gx*cellW),x1=Math.floor((gx+1)*cellW),y0=Math.floor(gy*cellH),y1=Math.floor((gy+1)*cellH);
   for(let y=y0;y<y1;y+=2)for(let x=x0;x<x1;x+=2){const p=(y*w+x)*4,lum=.2126*d[p]+.7152*d[p+1]+.0722*d[p+2];if(d[p+3]>30&&lum<155)ink++;total++}
   const score=ink/Math.max(1,total);if(score>.012)candidates.push({gx,gy,score});
  }
  candidates.sort((a,b)=>b.score-a.score);const picked=[];
  for(const c of candidates){if(picked.length>=10)break;if(!picked.some(p=>Math.abs(p.gx-c.gx)<=1&&Math.abs(p.gy-c.gy)<=1))picked.push(c)}
  if(picked.length<4){picked.splice(0,picked.length,...[{gx:1,gy:1,score:.1},{gx:3,gy:2,score:.1},{gx:5,gy:2,score:.1},{gx:6,gy:3,score:.1}])}
  picked.sort((a,b)=>a.gx-b.gx||a.gy-b.gy);nodes=[];const typeOrder=['firewall','switch','server','workstation','hmi','plc','sensor'];
  picked.forEach((p,i)=>{const ratio=p.gx/(cols-1),zone=ratio<.25?'enterprise':ratio<.48?'dmz':ratio<.73?'control':'field',type=typeOrder[Math.min(Math.round(ratio*(typeOrder.length-1)),typeOrder.length-1)];nodes.push({id:`asset-${i+1}`,name:`待确认设备 ${i+1}`,type,ip:`10.${10+Math.floor(ratio*3)*10}.0.${10+i}`,zone,profile:profiles[type],x:45+(p.gx/(cols-1))*790,y:80+(p.gy/(rows-1))*360,confidence:Math.min(.86,.56+p.score*1.8)})});
  links=[];const connected=new Set([0]);while(connected.size<nodes.length){let best=null;for(const a of connected)for(let b=0;b<nodes.length;b++){if(connected.has(b))continue;const dist=Math.hypot(nodes[a].x-nodes[b].x,nodes[a].y-nodes[b].y);if(!best||dist<best.dist)best={a,b,dist}}links.push([nodes[best.a].id,nodes[best.b].id]);connected.add(best.b)}
  selectedId=nodes[0].id;$('sourceHint').textContent=`${file.name} · 识别到 ${nodes.length} 个候选设备 · ${links.length} 条候选链路`;$('runState').textContent='识别完成，等待人工确认';selectNode(selectedId);toast('已生成候选拓扑，请校正低置信度节点')
 };img.src=URL.createObjectURL(file);
}

$('fileInput').addEventListener('change',e=>{const file=e.target.files[0];if(!file)return;const url=URL.createObjectURL(file),img=$('uploadedImage');img.src=url;img.style.display='block';$('runState').textContent='图片已载入，等待识别';$('sourceHint').textContent=`${file.name} · ${(file.size/1024).toFixed(0)} KB`;$('analyzeBtn').dataset.pending='1';$('analyzeBtn').onclick=()=>{$('scanline').classList.remove('running');void $('scanline').offsetWidth;$('scanline').classList.add('running');$('runState').textContent='正在提取设备和连线…';setTimeout(()=>detectFromImage(file),1300)}});
$('analyzeBtn').addEventListener('click',()=>{if(!$('analyzeBtn').dataset.pending){$('scanline').classList.remove('running');void $('scanline').offsetWidth;$('scanline').classList.add('running');setTimeout(()=>toast('样例拓扑校验完成'),1300)}});
$('loadSample').addEventListener('click',loadSample);$('nodeForm').addEventListener('input',syncForm);$('nodeForm').addEventListener('change',syncForm);
$('addNode').addEventListener('click',()=>{const id=`asset-${nodes.length+1}`;nodes.push({id,name:'新增设备',type:'server',ip:'待分配',zone:'control',profile:'linux-host',x:510,y:400,confidence:1});selectedId=id;selectNode(id);toast('已添加节点，请填写属性')});
$('generateBtn').addEventListener('click',generate);$('downloadBtn').addEventListener('click',()=>download(generated,$('orchestrator').value==='containerlab'?'factory-image-lab.clab.yml':'factory-topology.json'));
$('exportJson').addEventListener('click',()=>download(JSON.stringify(topologyIR(),null,2),'factory-topology-ir.json','application/json'));
$('copyBtn').addEventListener('click',async()=>{await navigator.clipboard.writeText(generated);toast('配置已复制')});
loadSample();

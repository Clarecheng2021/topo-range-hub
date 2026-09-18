const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../dist/service.js'), 'utf8');
const projects = new Map();
function session(hash = '') {
  const elements = {};
  function element(id) { return elements[id] ||= {
    hidden: id === 'projectEditor', style: {}, children: [], listeners: {}, classList: { toggle() {}, remove() {}, add() {} },
    addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); },
    setAttribute() {}, replaceChildren(...items) { this.children = items; }, append(...items) { this.children.push(...items); },
  }; }
  const storage = new Map();
  const context = {
    $: element, window: {}, console, setTimeout, setInterval, clearInterval,
    location: { hash, pathname: '/', search: '' },
    nodes: [], links: [], zoneDefs: [], zoneColors: {}, profiles: {}, selectedId: null,
    document: { createElement: () => element(`dynamic-${Math.random()}`), querySelectorAll: () => [{classList:{add(){}}},{classList:{add(){}}}] },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
    projectStore: async (action, value) => {
      if (action === 'put') { projects.set(value.id, structuredClone(value)); return value.id; }
      if (action === 'list') return structuredClone([...projects.values()]);
      return structuredClone(projects.get(value));
    },
    fetch() { throw new Error('local project restore must not call GLM'); },
    URL: { createObjectURL: file => `blob:${file.name}`, revokeObjectURL() {} }, toast() {},
  };
  context.history = { replaceState(a,b,url) { context.location.hash = url.includes('#') ? url.slice(url.indexOf('#')) : ''; } };
  context.resetForUpload = () => { context.nodes=[];context.links=[];context.zoneDefs=[]; };
  context.topologyIR = () => structuredClone({source:{kind:'canvas',image_size:{width:1320,height:760}}, nodes:context.nodes.map(n=>({...n,position:{x:n.x,y:n.y}})),links:context.links.map((l,i)=>({id:`l${i}`,source:l[0],target:l[1]})),zones:[]});
  context.selectNode = context.render = () => context.window.onTopologyChanged?.();
  vm.runInNewContext(code, context);
  return { context, element };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
async function main() {
  const first = session(); await settle();
  await first.element('fileInput').listeners.change[0]({target:{files:[{name:'new.png',size:1024}]}});
  const id = [...projects.keys()][0];
  first.context.nodes = [{id:'a',name:'手工审核设备',type:'plc',x:245,y:380},{id:'b',name:'HMI',type:'hmi',x:450,y:390}];
  first.context.links = [['a','b','ethernet']];
  first.context.window.onTopologyChanged(); await settle();
  assert.equal(projects.get(id).topology.nodes[0].position.x,245);
  const refreshed = session(first.context.location.hash); await settle();
  assert.equal(refreshed.element('uploadedImage').src,'blob:new.png');
  assert.equal(refreshed.context.nodes[0].name,'手工审核设备');
  assert.equal(refreshed.context.nodes[0].x,245);
  assert.equal(refreshed.context.links.length,1);
  assert.equal(refreshed.element('projectEditor').hidden,false);
  const home = session(); await settle();
  assert.equal(home.element('projectEditor').hidden,true);
  assert.equal(home.context.nodes.length,0);
  assert.equal(home.element('recentProjects').children.length,1);
  await home.element('recentProjects').children[0].children.at(-1).listeners.click[0](); await settle();
  assert.equal(home.context.nodes[0].name,'手工审核设备');
  await home.element('fileInput').listeners.change[0]({target:{files:[{name:'another.png',size:1024}]}});
  assert.equal(projects.size,2);
  assert.equal(projects.get(id).topology.links.length,1);
  console.log('PASS: homepage stays blank; recent projects; refresh restores edits; new uploads preserve previous projects');
}
main().catch(error=>{console.error(error);process.exitCode=1;});

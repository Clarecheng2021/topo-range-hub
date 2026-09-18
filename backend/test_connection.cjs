const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../dist/waterplant.js'), 'utf8');
const functions = source.slice(source.indexOf('function connectionIssue()'), source.indexOf('function loadWaterPlant('));
const elements = {};
const context = {
  nodes: [{ id: 'a', name: 'PLC' }, { id: 'b', name: 'HMI' }], links: [], selectedId: 'a',
  linkMode: false, linkSource: null, linkTarget: null, dragging: null, dragMoved: false, generated: 'old yaml',
  $: id => elements[id] ||= { classList: { toggle() {} }, setAttribute() {}, replaceChildren() {} },
  document: { createElement: () => ({}) }, toast() {}, selectNode(id) { context.selectedId = id; },
};
context.render = () => context.updateConnectionUI();
vm.runInNewContext(functions, context);
context.beginConnection();
assert.equal(context.linkSource, 'a');
context.handleNodeClick({}, 'a');
assert.match(context.connectionIssue(), /同一台/);
context.confirmConnection();
assert.equal(context.links.length, 0);
context.handleNodeClick({}, 'b');
assert.equal(context.links.length, 0, 'choosing endpoints must not immediately create an edge');
assert.equal(elements.confirmConnection.disabled, false);
context.confirmConnection();
assert.equal(context.links.length, 1);
assert.equal(context.linkMode, false);
assert.equal(context.generated, '');
assert.equal(elements.downloadBtn.disabled, true);
context.beginConnection();
context.handleNodeClick({}, 'a');
assert.match(context.connectionIssue(), /已存在/);
context.confirmConnection();
assert.equal(context.links.length, 1);
context.cancelConnection();
assert.equal(context.linkSource, null);
assert.equal(context.linkTarget, null);
assert.equal(elements.connectionPanel.hidden, true);
console.log('PASS: preselected source; explicit confirmation; self and duplicate rejection; cancellation; stale deployment invalidation');

const assert = require('node:assert/strict');
require('../dist/topology-import.js');
const prepare = globalThis.prepareTopologyImport;
const graph = {
  source: { kind: 'canvas', image_size: { width: 1320, height: 760 } },
  zones: [{ id: 'z', name: '工控网', bbox: { x: 20, y: 25, width: 1000, height: 600 } }],
  nodes: [{ id: 'a', name: 'PLC', type: 'plc', zone: 'z', position: { x: 210, y: 310 }, profile: 'modbus-plc' },
    { id: 'b', name: '交换机', type: 'switch', zone: 'z', position: { x: 450, y: 350 } }],
  links: [{ id: 'edge', source: 'a', target: 'b' }],
};
const imported = prepare(JSON.parse(JSON.stringify(graph)));
assert.deepEqual(imported.nodes[0].position, graph.nodes[0].position);
assert.deepEqual(imported.zones[0].bbox, graph.zones[0].bbox);
assert.equal(imported.nodes[0].profile, 'modbus-plc');
const raw = prepare({ nodes: [{ id: 'a', label: 'PLC', type: 'plc-station', bbox: [10, 20, 50, 60] },
  { id: 'b', label: 'HMI' }], links: [{ id: 'L17', endpoints: ['a', 'b'] }] });
assert.deepEqual(raw.nodes[0].position, { x: 30, y: 40 });
assert.equal(raw.nodes[0].type, 'plc');
assert.equal(raw.links[0].id, 'L17');
assert.equal(raw.links[0].target, 'b');
assert.equal(raw.zones.length, 0, 'unpartitioned graph must not receive invented zones');
assert.equal(raw.nodes[0].zone, '');
assert.throws(() => prepare({ nodes: [{ id: 'a' }, { id: 'a' }], links: [] }), /重复设备/);
assert.throws(() => prepare({ nodes: [{ id: 'a' }], links: [{ source: 'a', target: 'missing' }] }), /不存在/);
assert.throws(() => prepare({ nodes: [{ id: 'a', position: { x: 'bad', y: 20 } }], links: [] }), /坐标/);
console.log('PASS: exported positions and profiles; GLM candidates; duplicate IDs; missing endpoints; invalid coordinates');

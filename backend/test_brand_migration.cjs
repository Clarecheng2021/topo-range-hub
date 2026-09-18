const assert = require('node:assert/strict');
const databases = new Map([
  ['factorytwin.projects', new Map([['projects', new Map([['old', {id:'old',name:'历史工程'}], ['shared', {id:'shared',name:'旧编辑'}]])]])],
  ['toporangehub.projects', new Map([['projects',new Map([['shared',{id:'shared',name:'新编辑'}]])],['meta',new Map()]])],
]);
globalThis.indexedDB = {
  open(name) {
    const request = {};
    queueMicrotask(() => {
      const upgrade = !databases.has(name);
      if (upgrade) databases.set(name,new Map());
      const stores = databases.get(name);
      request.result = {
        close() {}, createObjectStore(key) { stores.set(key,new Map()); },
        transaction(key) {
          const tx = {
            objectStore() {
              const store = stores.get(key);
              const result = value => { queueMicrotask(() => tx.oncomplete()); return {result:structuredClone(value)}; };
              return {
                get: id => result(store.get(id)), getAll: () => result([...store.values()]),
                put(value,id) { const key = id ?? value.id; store.set(key,structuredClone(value)); return result(key); },
              };
            },
          };
          return tx;
        },
      };
      if (upgrade) request.onupgradeneeded();
      request.onsuccess();
    });
    return request;
  },
};
require('../dist/project-store.js');
(async () => {
  const projects = await projectStore('list');
  assert.equal(projects.length,2);
  assert.equal((await projectStore('get','old')).name,'历史工程');
  assert.equal((await projectStore('get','shared')).name,'新编辑');
  await projectStore('put',{id:'old',name:'迁移后修改'});
  assert.equal((await projectStore('get','old')).name,'迁移后修改');
  assert.equal(databases.get('factorytwin.projects').get('projects').get('old').name,'历史工程');
  console.log('PASS: legacy project migration; existing new edits preserved; legacy database retained');
})().catch(error=>{console.error(error);process.exitCode=1;});

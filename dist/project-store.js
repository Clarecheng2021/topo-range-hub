/* TopoRangeHub engineering storage, with a non-destructive legacy migration. */
(() => {
  const open = name => new Promise((resolve, reject) => {
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('projects', { keyPath: 'id' });
      if (name === 'toporangehub.projects') request.result.createObjectStore('meta');
    };
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
  const operation = (db, storeName, action, value, key) => new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, action === 'put' ? 'readwrite' : 'readonly');
    const store = tx.objectStore(storeName);
    const request = action === 'put' ? (key === undefined ? store.put(value) : store.put(value, key)) : action === 'list' ? store.getAll() : store.get(value);
    tx.oncomplete = () => resolve(request.result);
    tx.onerror = tx.onabort = () => reject(tx.error);
  });
  let migration;
  async function migrate() {
    const db = await open('toporangehub.projects');
    let legacy;
    try {
      if (await operation(db, 'meta', 'get', 'legacyMigrated')) return;
      legacy = await open('factorytwin.projects');
      for (const project of await operation(legacy, 'projects', 'list')) {
        if (!(await operation(db, 'projects', 'get', project.id))) await operation(db, 'projects', 'put', project);
      }
      await operation(db, 'meta', 'put', true, 'legacyMigrated');
    } finally { legacy?.close(); db.close(); }
  }
  globalThis.projectStore = async (action, value) => {
    migration ||= migrate().catch(error => { migration = null; throw error; });
    await migration;
    const db = await open('toporangehub.projects');
    try { return await operation(db, 'projects', action, value); } finally { db.close(); }
  };
})();

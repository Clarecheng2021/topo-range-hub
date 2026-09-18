/* Accept exported project graphs and raw visual-model candidates. */
(() => {
  function prepareTopologyImport(value) {
    if (!value || typeof value !== 'object' || !Array.isArray(value.nodes) || !Array.isArray(value.links)) {
      throw new Error('JSON 必须包含 nodes 和 links 数组');
    }
    if (!value.nodes.length) throw new Error('拓扑中没有设备');
    if (value.nodes.length > 5000 || value.links.length > 20000) throw new Error('拓扑规模过大');
    const ids = new Set();
    const zoneIds = new Set();
    const bbox = box => {
      if (!box) return undefined;
      const result = Array.isArray(box)
        ? { x: box[0], y: box[1], width: box[2] - box[0], height: box[3] - box[1] }
        : { x: box.x, y: box.y, width: box.width, height: box.height };
      if (!Object.values(result).every(Number.isFinite) || result.width < 0 || result.height < 0) throw new Error('设备或区域坐标无效');
      return result;
    };
    const id = (item, label) => {
      if (typeof item !== 'string' || !item.trim()) throw new Error(`${label} ID 必须是非空字符串`);
      return item;
    };
    if (value.zones !== undefined && !Array.isArray(value.zones)) throw new Error('zones 必须是数组');
    const zones = (value.zones || []).map(zone => {
      const key = id(zone?.id, '区域');
      if (zoneIds.has(key)) throw new Error(`重复区域 ID：${key}`);
      zoneIds.add(key);
      return { ...zone, id: key, name: String(zone.name || key), bbox: bbox(zone.bbox) };
    });
    const aliases = { 'plc-station': 'plc', 'plc-substation': 'plc', 'hmi-tag': 'hmi' };
    const nodes = value.nodes.map((node, index) => {
      const key = id(node?.id, '设备');
      if (ids.has(key)) throw new Error(`重复设备 ID：${key}`);
      ids.add(key);
      const box = bbox(node.bbox);
      const position = node.position || (Number.isFinite(node.x) && Number.isFinite(node.y) ? { x: node.x, y: node.y } :
        box ? { x: box.x + box.width / 2, y: box.y + box.height / 2 } : undefined);
      if (position && (!Number.isFinite(position.x) || !Number.isFinite(position.y))) throw new Error(`设备 ${key} 坐标无效`);
      const zone = String(node.zone || '');
      return { ...node, id: key, name: String(node.name || node.label || key), type: aliases[node.type] || node.type || 'unknown',
        zone, bbox: box, position: position || { x: 100 + index % 8 * 150, y: 100 + Math.floor(index / 8) * 110 } };
    });
    const linkIds = new Set();
    const links = value.links.map((link, index) => {
      const source = link?.source ?? link?.endpoints?.[0] ?? (Array.isArray(link) ? link[0] : undefined);
      const target = link?.target ?? link?.endpoints?.[1] ?? (Array.isArray(link) ? link[1] : undefined);
      const key = link?.id || `link-${index + 1}`;
      if (linkIds.has(key)) throw new Error(`重复连线 ID：${key}`);
      linkIds.add(key);
      if (!ids.has(source) || !ids.has(target)) throw new Error(`连线 ${key} 引用了不存在的设备`);
      return { ...link, id: key, source, target, protocol: link.protocol || (Array.isArray(link) ? link[2] : undefined) || 'Ethernet' };
    });
    const size = value.source?.image_size || value.image_size || { width: 1320, height: 760 };
    if (!Number.isFinite(size.width) || !Number.isFinite(size.height) || size.width <= 0 || size.height <= 0) throw new Error('图像或画布尺寸无效');
    return { ...value, nodes, links, zones, source: { ...value.source, image_size: size } };
  }
  globalThis.prepareTopologyImport = prepareTopologyImport;
})();

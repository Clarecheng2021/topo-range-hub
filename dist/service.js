/* Connect the existing editable canvas to the containerized GLM API. */
(() => {
  // Migrate preferences and the old single-project pointer once.
  for (const key of ['reasoningEffort', 'logCollapsed', 'activeJob', 'draftToken']) {
    try {
      const oldKey = `factorytwin.${key}`, newKey = `toporangehub.${key}`;
      const oldValue = localStorage.getItem(oldKey);
      if (oldValue !== null && localStorage.getItem(newKey) === null) localStorage.setItem(newKey, oldValue);
      if (oldValue !== null) localStorage.removeItem(oldKey);
    } catch {}
  }
  const palette = ['#9c7cff', '#35d6b2', '#5aa9ff', '#ffb15a', '#ff6b8a'];
  let selectedFile = null;
  let runningJobId = null;
  let selectionVersion = 0;
  let imageUrl = null;
  let clockTimer = null;
  let currentProject = null;
  let restoringProject = false;
  let lastGraph = '';
  let saveSequence = 0;
  let projectSaveChain = Promise.resolve();
  let previewUrls = [];

  function showEditor() {
    $('projectHome').hidden = true; $('projectEditor').hidden = false;
    $('backToProjects').hidden = false; $('saveState').hidden = false;
  }

  function queueProjectSave() {
    if (!currentProject || restoringProject) return projectSaveChain;
    const snapshot = { ...currentProject, topology: topologyIR(), updatedAt: new Date().toISOString() };
    currentProject = snapshot;
    const sequence = ++saveSequence;
    $('saveState').textContent = '正在保存…';
    projectSaveChain = projectSaveChain.catch(() => {}).then(() => projectStore('put', snapshot)).then(() => {
      if (currentProject?.id === snapshot.id && sequence === saveSequence) $('saveState').textContent = '已自动保存';
    }).catch(error => {
      if (currentProject?.id === snapshot.id) $('saveState').textContent = '自动保存失败，请导出 JSON';
      throw error;
    });
    // Keep failed saves visible without an unhandled rejection on render.
    projectSaveChain.catch(() => {});
    return projectSaveChain;
  }

  window.onTopologyChanged = () => {
    if (!currentProject || restoringProject) return;
    const signature = JSON.stringify(topologyIR());
    if (signature === lastGraph) return;
    lastGraph = signature;
    queueProjectSave();
  };

  function newProject(file, kind) {
    currentProject = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, name: file.name,
      file, kind, jobId: null, jobActive: false, createdAt: new Date().toISOString() };
    lastGraph = ''; showEditor();
    history.replaceState(null, '', `#project=${encodeURIComponent(currentProject.id)}`);
  }

  async function renderRecentProjects() {
    previewUrls.forEach(url => URL.revokeObjectURL(url)); previewUrls = [];
    const list = $('recentProjects'); list.replaceChildren();
    const projects = await projectStore('list');
    projects.sort((a,b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
    if (!projects.length) { list.textContent = '还没有保存的项目，上传图片或导入 JSON 开始。'; return; }
    for (const project of projects) {
      const card = document.createElement('article'); card.className = 'project-card';
      if (project.kind === 'image' && project.file) {
        const img = document.createElement('img'); img.src = URL.createObjectURL(project.file); img.alt = project.name;
        previewUrls.push(img.src); card.append(img);
      }
      const title = document.createElement('strong'); title.textContent = project.name;
      const details = document.createElement('p'); details.textContent = `${project.topology?.nodes?.length || 0} 台设备 · ${project.topology?.links?.length || 0} 条链路 · ${project.updatedAt ? new Date(project.updatedAt).toLocaleString() : '旧版本工程'}`;
      const button = document.createElement('button'); button.className = 'button secondary'; button.textContent = '继续编辑';
      button.addEventListener('click', () => openProject(project.id));
      card.append(title, details, button); list.append(card);
    }
  }

  async function openProject(id) {
    const version = ++selectionVersion;
    try {
      const project = await projectStore('get', id);
      if (version !== selectionVersion) return;
      if (!project) throw new Error('工程不存在');
      restoringProject = true; currentProject = null;
      resetForUpload(); resetClock(); renderJobEvents([]);
      $('outputPanel').hidden = true; $('downloadBtn').disabled = true;
      selectedFile = project.kind === 'image' ? project.file : null;
      if (selectedFile) displayFile(selectedFile);
      else $('showOriginal').disabled = true;
      if (Array.isArray(project.topology?.nodes)) mapTopology(project.topology, project.name, true);
      $('sourceHint').textContent = `${project.name} · 已恢复工程`;
      $('runState').textContent = project.jobActive ? '正在恢复识别任务…' : project.topology?.nodes?.length ? '工程已恢复，可继续编辑' : '原图已恢复，等待分析';
      currentProject = project; lastGraph = JSON.stringify(topologyIR()); restoringProject = false;
      showEditor(); setRunningJob(null); $('saveState').textContent = '已自动保存';
      history.replaceState(null, '', `#project=${encodeURIComponent(id)}`);
      window.currentTopologyJobId = project.jobId;
      if (project.jobId && project.jobActive) await watchJob(project.jobId, project.name, version);
    } catch (error) { restoringProject = false; toast(`工程恢复失败：${error.message}`); }
  }

  $('homeUpload').addEventListener('click', () => $('fileInput').click());
  $('homeImport').addEventListener('click', () => $('jsonInput').click());
  $('backToProjects').addEventListener('click', async () => {
    try { await queueProjectSave(); } catch { toast('保存失败，请导出 JSON 后再返回'); return; }
    ++selectionVersion; currentProject = null; selectedFile = null;
    resetClock(); setRunningJob(null); resetForUpload(); renderJobEvents([]);
    $('projectEditor').hidden = true; $('projectHome').hidden = false;
    $('backToProjects').hidden = true; $('saveState').hidden = true;
    history.replaceState(null, '', location.pathname + location.search);
    try { await renderRecentProjects(); } catch { toast('项目列表读取失败'); }
  });
  try {
    const savedEffort = localStorage.getItem('toporangehub.reasoningEffort');
    $('reasoningEffort').value = ['low', 'high', 'max'].includes(savedEffort) ? savedEffort : 'low';
  } catch { $('reasoningEffort').value = 'low'; }
  $('reasoningEffort').addEventListener('change', () => {
    try { localStorage.setItem('toporangehub.reasoningEffort', $('reasoningEffort').value); } catch {}
  });

  function resetClock() {
    if (clockTimer !== null) clearInterval(clockTimer);
    clockTimer = null;
    $('analysisElapsed').textContent = '耗时 00:00';
  }

  function updateClock(job) {
    resetClock();
    const start = Date.parse(job.started_at || '');
    const terminal = ['completed', 'failed', 'cancelled'].includes(job.status);
    const finish = Date.parse(job.finished_at || job.updated_at || '');
    if (!Number.isFinite(start)) {
      $('analysisElapsed').textContent = terminal ? '历史任务未记录耗时' : '等待开始';
      return;
    }
    const tick = () => {
      const seconds = Math.max(0, Math.floor(((terminal ? finish : Date.now()) - start) / 1000));
      const minutes = Math.floor(seconds / 60);
      $('analysisElapsed').textContent = `耗时 ${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    };
    tick();
    if (!terminal) clockTimer = setInterval(tick, 1000);
  }

  function draftStore(mode, file, token) {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('factorytwin.uploads', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('files');
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction('files', mode);
        const store = transaction.objectStore('files');
        const operation = mode === 'readwrite' ? store.put({ file, token }, 'current') : store.get('current');
        transaction.oncomplete = () => { const result = operation.result; db.close(); resolve(result); };
        transaction.onerror = () => { db.close(); reject(transaction.error); };
        transaction.onabort = () => { db.close(); reject(transaction.error); };
      };
    });
  }

  function displayFile(file) {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    imageUrl = URL.createObjectURL(file);
    $('uploadedImage').src = imageUrl;
    $('uploadedImage').style.display = 'block';
    $('uploadedImage').classList.remove('original');
    $('showOriginal').disabled = false;
    $('showOriginal').textContent = '显示原图';
    $('sourceHint').textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
  }

  function setRunningJob(jobId) {
    runningJobId = jobId;
    $('stopAnalysisBtn').hidden = !jobId;
    $('stopAnalysisBtn').disabled = false;
    $('stopAnalysisBtn').textContent = '停止识别';
    $('analyzeBtn').disabled = Boolean(jobId) || !selectedFile;
    $('fileInput').disabled = Boolean(jobId);
    $('jsonInput').disabled = Boolean(jobId);
    $('reasoningEffort').disabled = Boolean(jobId);
  }

  $('stopAnalysisBtn').addEventListener('click', async () => {
    if (!runningJobId) return;
    const jobId = runningJobId;
    $('stopAnalysisBtn').disabled = true;
    $('stopAnalysisBtn').textContent = '正在停止…';
    try {
      const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || '停止识别失败');
      // Polling reads the terminal state and preserves the final partial output.
    } catch (error) {
      toast(error.message || '停止识别失败，请重试');
      if (runningJobId === jobId) {
        $('stopAnalysisBtn').disabled = false;
        $('stopAnalysisBtn').textContent = '停止识别';
      }
    }
  });

  function setLogCollapsed(collapsed) {
    $('analysisLog').classList.toggle('collapsed', collapsed);
    $('analysisLogBody').hidden = collapsed;
    $('toggleAnalysisLog').setAttribute('aria-expanded', String(!collapsed));
    $('toggleAnalysisLog').textContent = collapsed ? '展开 ▴' : '收起 ▾';
  }

  let logCollapsed = false;
  try { logCollapsed = localStorage.getItem('toporangehub.logCollapsed') === 'true'; } catch {}
  setLogCollapsed(logCollapsed);
  $('toggleAnalysisLog').addEventListener('click', () => {
    logCollapsed = !logCollapsed;
    setLogCollapsed(logCollapsed);
    try { localStorage.setItem('toporangehub.logCollapsed', String(logCollapsed)); } catch {}
  });

  function renderJobEvents(events = []) {
    events = events.filter(event => !/服务仍在等待结构化结果|暂未返回结构化片段/.test(event.stage || ''));
    const panel = $('analysisLog');
    const list = $('analysisEvents');
    panel.hidden = !events.length;
    list.replaceChildren(...events.map(event => {
      const item = document.createElement('li');
      item.textContent = event.stage;
      return item;
    }));
    const body = $('analysisLogBody');
    body.scrollTop = body.scrollHeight;
  }

  function canvasType(type) {
    return ['internet', 'firewall', 'router', 'switch', 'server', 'workstation', 'hmi', 'plc', 'camera', 'security', 'display', 'sensor'].includes(type)
      ? type : type === 'industrial_switch' ? 'switch' : 'server';
  }

  function mapTopology(topology, filename = '已恢复的识别结果', imported = false) {
    linkMode=false;linkSource=null;linkTarget=null;dragging=null;dragMoved=false;
    const size = topology.source?.image_size || { width: 1672, height: 941 };
    const sx = 1320 / Math.max(Number(size.width) || 1672, 1);
    const sy = 760 / Math.max(Number(size.height) || 941, 1);
    const canvasCoordinates = topology.source?.kind === 'canvas';
    const sourceZones = topology.zones || [];
    zoneDefs = sourceZones.map((zone, index) => {
      const box = zone.bbox || { x: 20 + index * 18, y: 25 + index * 18, width: 1260 - index * 36, height: 720 - index * 36 };
      zoneColors[zone.id] = palette[index % palette.length];
      return { id: zone.id, name: zone.name, x: box.x * sx + (canvasCoordinates ? 0 : 20), y: box.y * sy + (canvasCoordinates ? 0 : 25), w: Math.max(box.width * sx, 160), h: Math.max(box.height * sy, 120) };
    });
    const zoneSelect = $('nodeZone');
    zoneSelect.replaceChildren(...zoneDefs.map(zone => {
      const option = document.createElement('option');
      option.value = zone.id; option.textContent = zone.name;
      return option;
    }));
    if (!zoneDefs.length) {
      const option = document.createElement('option');
      option.value = ''; option.textContent = '未划分区域';
      zoneSelect.append(option);
    }
    zoneSelect.disabled = !zoneDefs.length;
    nodes = topology.nodes.map((node, index) => {
      const box = node.bbox || {};
      const position = node.position || { x: Number(box.x) + Number(box.width) / 2 || 80 + (index % 8) * 145, y: Number(box.y) + Number(box.height) / 2 || 120 + Math.floor(index / 8) * 100 };
      const type = canvasType(node.type);
      return {
        id: node.id, name: node.name, type, zone: node.zone || '',
        ip: node.ip || '待分配 IP', x: position.x * sx, y: position.y * sy,
        confidence: Number.isFinite(node.confidence) ? node.confidence : .75,
        profile: node.profile || profiles[type] || 'linux-host', evidence: node.evidence
      };
    });
    links = topology.links.map(link => [link.source, link.target, link.protocol || link.medium || 'Ethernet']);
    selectedId = nodes[0]?.id || null;
    currentView = { x: 0, y: 0, w: 1400, h: 820 };
    $('sourceHint').textContent = `${filename} · ${imported ? 'JSON 导入' : 'GLM 识别'} ${nodes.length} 台设备 · ${links.length} 条链路`;
    $('runState').textContent = imported ? 'JSON 矢量拓扑已导入，可编辑或生成部署配置' : 'GLM 拓扑候选已生成，等待审核';
    $('exportJson').disabled = false;
    document.querySelectorAll('.workflow-step')[1].classList.add('active');
    if (selectedId) selectNode(selectedId); else render();
  }

  async function analyzeWithService() {
    if (!selectedFile) { toast('请先上传 PNG、JPEG 或 WebP 拓扑图'); return; }
    const button = $('analyzeBtn');
    const filename = selectedFile.name;
    const version = selectionVersion;
    button.disabled = true;
    $('fileInput').disabled = true;
    $('jsonInput').disabled = true;
    $('reasoningEffort').disabled = true;
    $('backToProjects').disabled = true;
    $('runState').textContent = 'GLM 正在识别区域、设备与可见连线…';
    $('scanline').classList.remove('running'); void $('scanline').offsetWidth; $('scanline').classList.add('running');
    const data = new FormData();
    data.append('image', selectedFile);
    data.append('scope', '生产工控网');
    data.append('reasoning_effort', $('reasoningEffort').value);
    try {
      resetClock();
      $('modelOutput').textContent = '等待模型返回识别结果正文…';
      renderJobEvents([{ progress: 0, stage: '正在上传图片到识别服务' }]);
      const response = await fetch('/api/analyze', { method: 'POST', body: data });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || '识别服务请求失败');
      window.currentTopologyJobId = body.job_id;
      currentProject.jobId = body.job_id; currentProject.jobActive = true;
      setRunningJob(body.job_id);
      try { await queueProjectSave(); } catch { toast('识别任务已启动，但自动保存失败，请完成后导出 JSON'); }
      $('backToProjects').disabled = false;
      await watchJob(body.job_id, filename, version);
    } catch (error) {
      const message = error.message || '识别服务不可用';
      $('runState').textContent = `识别失败：${message}`;
      toast(message);
    } finally {
      if (version === selectionVersion) {
        setRunningJob(null);
        $('backToProjects').disabled = false;
        button.disabled = !selectedFile;
        $('scanline').classList.remove('running');
      }
    }
  }

  async function watchJob(jobId, filename = selectedFile?.name, version = selectionVersion) {
    while (version === selectionVersion) {
      const response = await fetch(`/api/jobs/${jobId}`);
      const job = await response.json();
      if (version !== selectionVersion) return;
      if (response.status === 503) {
        await new Promise(resolve => setTimeout(resolve, 500));
        continue;
      }
      if (!response.ok) throw new Error(job.detail || '无法读取识别进度');
      updateClock(job);
      $('runState').textContent = job.stage;
      renderJobEvents(job.events || [{ progress: job.progress, stage: job.stage }]);
      if (job.status === 'running' || job.status === 'queued') {
        if (runningJobId !== jobId) setRunningJob(jobId);
      } else {
        setRunningJob(null);
      }
      const outputResponse = await fetch(`/api/jobs/${jobId}/output`, { cache: 'no-store' });
      if (outputResponse.ok) {
        const output = await outputResponse.text();
        if (version !== selectionVersion) return;
        $('modelOutput').textContent = output || '等待模型返回识别结果正文…';
        $('modelOutput').scrollTop = $('modelOutput').scrollHeight;
      }
      if (job.status === 'completed') {
        const topologyResponse = await fetch(`/api/jobs/${jobId}/topology`);
        const topology = await topologyResponse.json();
        if (version !== selectionVersion) return;
        if (!topologyResponse.ok) throw new Error(topology.detail || '拓扑结果读取失败');
        mapTopology(topology, filename);
        if (currentProject) { currentProject.jobActive = false; await queueProjectSave(); }
        toast('GLM 识别完成；请审核低置信度链路后导出靶场配置');
        return;
      }
      if (job.status === 'failed') {
        if (currentProject) { currentProject.jobActive = false; await queueProjectSave(); }
        throw new Error(job.error || 'GLM 识别失败');
      }
      if (job.status === 'cancelled') {
        if (currentProject) { currentProject.jobActive = false; await queueProjectSave(); }
        $('scanline').classList.remove('running');
        toast('识别已停止，可点击分析按钮重新识别');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
  }

  $('fileInput').addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    const version = ++selectionVersion;
    window.currentTopologyJobId = null;
    currentProject = null;
    selectedFile = file;
    setRunningJob(null);
    resetForUpload();
    resetClock();
    renderJobEvents([]);
    $('outputPanel').hidden = true;
    $('downloadBtn').disabled = true;
    displayFile(file);
    newProject(file, 'image');
    $('runState').textContent = '新图片已载入，正在保存…';
    $('analyzeBtn').disabled = true;
    try {
      await queueProjectSave();
      if (version !== selectionVersion) return;
      $('runState').textContent = '图片已保存，等待分析';
    } catch {
      if (version !== selectionVersion) return;
      $('runState').textContent = '图片已载入，但浏览器保存失败，刷新前请先开始分析';
    }
    $('analyzeBtn').disabled = false;
  });
  $('analyzeBtn').onclick = analyzeWithService;

  function displayImportedTopology(topology, filename) {
    selectedFile = null;
    window.currentTopologyJobId = null;
    setRunningJob(null);
    resetForUpload();
    resetClock();
    renderJobEvents([]);
    $('outputPanel').hidden = true;
    $('downloadBtn').disabled = true;
    $('showOriginal').disabled = true;
    mapTopology(topology, filename, true);
  }

  $('jsonInput').addEventListener('change', async event => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file || runningJobId) return;
    const previousVersion = selectionVersion;
    try {
      if (file.size > 12 * 1024 * 1024) throw new Error('JSON 文件不能超过 12 MB');
      const topology = prepareTopologyImport(JSON.parse((await file.text()).replace(/^\uFEFF/, '')));
      if (selectionVersion !== previousVersion) return;
      ++selectionVersion;
      currentProject = null;
      displayImportedTopology(topology, file.name);
      newProject(file, 'json');
      try {
        await queueProjectSave();
        toast('拓扑 JSON 已导入并保存，刷新后可恢复');
      } catch {
        toast('拓扑已导入，但浏览器保存失败，请导出后保存');
      }
    } catch (error) {
      toast(`JSON 导入失败：${error.message}`);
    }
  });

  async function initializeProjects() {
    $('homeUpload').disabled = true; $('homeImport').disabled = true;
    $('fileInput').disabled = true; $('jsonInput').disabled = true;
    try {
      // Migrate the previous single saved selection into a selectable project.
      const token = localStorage.getItem('toporangehub.draftToken');
      const saved = JSON.parse(localStorage.getItem('toporangehub.activeJob') || 'null');
      const id = token ? `legacy-draft-${token}` : saved?.jobId ? `legacy-job-${saved.jobId}` : null;
      if (id && !(await projectStore('get', id))) {
        let file, topology = null, kind = 'image';
        if (token) {
          const draft = await draftStore('readonly');
          if (draft?.token === token) file = draft.file;
          if (file && /\.json$/i.test(file.name)) { kind = 'json'; topology = prepareTopologyImport(JSON.parse(await file.text())); }
        } else {
          const response = await fetch(`/api/jobs/${saved.jobId}/source`);
          if (response.ok) file = new File([await response.blob()], saved.filename || 'upload.png');
          const result = await fetch(`/api/jobs/${saved.jobId}/topology`);
          if (result.ok) topology = await result.json();
        }
        if (file) await projectStore('put', { id, file, name: file.name, kind, topology,
          jobId: token ? null : saved.jobId, jobActive: !token && !topology, updatedAt: new Date().toISOString() });
      }
      if (!id || await projectStore('get', id)) {
        localStorage.removeItem('toporangehub.activeJob'); localStorage.removeItem('toporangehub.draftToken');
      }
      await renderRecentProjects();
      const match = location.hash.match(/^#project=(.+)$/);
      if (match) await openProject(decodeURIComponent(match[1]));
      else $('runState').textContent = '请选择新建或继续编辑项目';
    } catch (error) { $('recentProjects').textContent = `工程存储暂不可用：${error.message}`; }
    finally {
      $('homeUpload').disabled = false; $('homeImport').disabled = false;
      if (!runningJobId) { $('fileInput').disabled = false; $('jsonInput').disabled = false; }
    }
  }
  initializeProjects();
})();

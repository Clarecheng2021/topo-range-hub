# TopoRangeHub

TopoRangeHub 从用户上传的工控拓扑图生成可编辑矢量拓扑和可部署网络配置，支持 GLM 识别、拓扑 JSON 导入、手动审核与浏览器本地工程自动保存：

1. 上传 PNG、JPEG 或 WebP 拓扑图，或导入拓扑 JSON。
2. 根据实际图片识别设备、连线和可见区域划分。
3. 生成可点击、拖拽、增删和重新连接的设备拓扑。
4. 在右侧校正设备类型、IP、安全区域和运行模板。
5. 导出统一拓扑 JSON，或在人工确认后启动对应的 Docker 隔离虚拟靶场。
6. 在 Docker 运行时中创建隔离的虚拟节点和链路，作为网络安全测试环境。

## 本地查看

直接打开 `dist/index.html`，或在 `dist` 目录启动任意静态文件服务器。

## Docker 一键运行与隔离靶场

仅需 Docker Desktop；不需要安装 Containerlab、WSL 或 Claude Code。创建 `.env` 后启动：

```dotenv
ZHIPUAI_API_KEY=替换为你的智谱开放平台API密钥
ZHIPU_VISION_MODEL=glm-5.3-flash
```

```powershell
docker compose up --build -d
```

打开 `http://localhost:8080`：上传图片 → GLM 识别 → 人工校正 → “生成部署预览” → “启动隔离靶场”。

运行时由 `range-engine` 控制一个内部 Docker 守护进程，网页和主服务都不会挂载宿主机 Docker Socket。每个生成节点以 `NetworkMode=none` 启动，仅按审核后的拓扑连接到内部链路网络；默认没有宿主机端口映射、生产网桥和互联网出口。`range-docker` 使用 Docker-in-Docker 的 `privileged` 模式，因此只应在受信任的本地实验机或专用靶场主机运行。
## 本地解析流水线（实验）

对图片 `test1.png` 的本地验证流程如下。所有输出均为候选结果，必须人工复核：

```powershell
python backend\ocr_local.py "C:\Users\Administrator\Desktop\test1.png"
python backend\detect_lines.py "C:\Users\Administrator\Desktop\test1.png" artifacts\ocr\test1_res.json --output artifacts\lines\test1-v3
python backend\detect_devices.py "C:\Users\Administrator\Desktop\test1.png" artifacts\ocr\test1_res.json --output artifacts\devices\test1.json
python backend\reconstruct_links.py "C:\Users\Administrator\Desktop\test1.png" artifacts\devices\test1.json artifacts\lines\test1-v3\line-candidates.json --output artifacts\topology\test1-link-candidates.json
```

其中 `detect_devices.py` 是用于当前 Demo 图形风格的颜色/形状基线检测器；后续可把它替换为训练完成的 YOLO 图标检测器。`reconstruct_links.py` 只在一条线的两个端点都靠近不同设备候选框时才生成链路候选。

### 多模态图像解析（推荐用于未知拓扑图）

传统直线检测无法可靠地区分链路、设备边框和区域边界。配置视觉模型 API 密钥后，可将原图和 OCR 证据一起提交给多模态解析器，由模型按完整连线路径输出候选图谱：

```powershell
$env:OPENAI_API_KEY = "你的 API 密钥"
python backend\vlm_topology.py "C:\Users\Administrator\Desktop\test1.png" --ocr-json artifacts\ocr\test1_res.json --output artifacts\topology\test1-vlm-candidates.topology.json
```

可用环境变量 `OPENAI_VISION_MODEL` 指定模型，以及 `OPENAI_BASE_URL` 指定兼容的 Responses API 地址。输出始终标记为 `unreviewed`，不会直接触发靶场部署。

## 最终产品基线

最终产品不是单纯的拓扑绘图工具，而是从非结构化图片生成隔离、可操作靶场的工程闭环：

```text
PNG/JPG/PDF
  -> 图像预处理
  -> OCR + 设备检测 + 连线追踪 + 多模态语义校验
  -> 统一拓扑 Graph JSON
  -> 人工校正与置信度复核
  -> 场景编译
  -> Docker 隔离靶场 / VM / 物理设备适配器
  -> 部署、健康检查与结果回传
```

详细能力边界、模块拆分、版本路线和验收标准见 [docs/PRODUCT_BASELINE.md](docs/PRODUCT_BASELINE.md)。统一拓扑中间表示见 [topology-schema/topology.schema.json](topology-schema/topology.schema.json)。

任何自动生成环境默认关闭互联网出口并禁止桥接生产网；部署真实厂商镜像、Windows 虚机或物理 PLC 时，必须由资源适配器检查镜像授权、资源可用性和隔离策略。

## Docker 最终产品（GLM 直连）

容器化版本不依赖 Claude Code、MCP、PP-OCR 或本机 Python。浏览器上传 PNG/JPEG/WebP 后，后端直接调用智谱开放平台的视觉模型，标准化为统一拓扑 JSON；审核后可启动对应的 Docker 隔离虚拟靶场。

1. 在智谱开放平台创建**标准 API Key**（不要使用 GLM Coding Plan 的工具套餐 Key）。
2. 安装 Docker Desktop 并启动 Docker Engine。
3. 在项目目录创建 `.env`，内容如下：

```dotenv
ZHIPUAI_API_KEY=替换为你的智谱开放平台API密钥
ZHIPU_VISION_MODEL=glm-5.3-flash
```

4. 构建并启动：

```powershell
docker compose up --build -d
```

5. 打开 `http://localhost:8080`，上传拓扑图，点击“生成设备拓扑”。

结果文件保存在 Docker 逻辑卷 `toporangehub-data` 中。为兼容升级，默认仍映射原有物理数据卷，可通过 `TOPORANGEHUB_DATA_VOLUME` 指定已有卷名。服务会在用户点击“启动隔离靶场”并确认后，向内部受控运行时提交审核拓扑；它不会连接宿主机 Docker Socket、生产网卡或互联网。

### GLM 标准化器（已有候选结果）

将 Claude/GLM 视觉分析产生的候选 JSON 转成统一中间表示：

```powershell
python backend\normalize_glm_topology.py artifacts\topology\test1-glm-candidates.topology.json --output artifacts\topology\test1-glm-normalized.topology.json
```

它会将数组 bbox 转成标准对象、将 `endpoints` 转为 `source`/`target`、删除重复母线边 `L17`，并将 `L08` 和中部 ProfiNet 短分支保留为低置信待审核链路。

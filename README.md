# 厂域镜像 Demo

该 Demo 演示从复杂工厂拓扑图到可操作设备图和可部署网络配置的闭环。当前内置了“钟山水厂网络拓扑图”的完整识别结果：

1. 上传 PNG、JPEG、WebP 或 SVG 拓扑图。
2. 识别办公网、集团边界、安防网、泵房和生产工控网等区域。
3. 生成可点击、拖拽、增删和重新连接的设备拓扑。
4. 在右侧校正设备类型、IP、安全区域和运行模板。
5. 导出统一拓扑 JSON 或包含全部当前设备及链路的 Containerlab YAML。
6. 在隔离的 Linux/Docker 测试主机上部署真实网络命名空间和 veth 链路。

## 本地查看

直接打开 `dist/index.html`，或在 `dist` 目录启动任意静态文件服务器。

## 部署示例环境

需要 Linux、Docker 和 Containerlab。确认测试主机未桥接生产网络后，在 PowerShell 中运行：

```powershell
.\scripts\deploy-demo.ps1
```

当前版本内置的是水厂复杂拓扑识别模板，并非通用 OCR/视觉模型。它不会声称从图片中恢复未标注的系统版本、端口配置、PLC 程序或工艺逻辑。要识别任意同类图片，下一步需要接入服务端 OCR、图标检测、连线追踪和多模态语义校验服务。

## 最终产品基线

最终产品不是单纯的拓扑绘图工具，而是从非结构化图片生成隔离、可操作靶场的工程闭环：

```text
PNG/JPG/PDF
  -> 图像预处理
  -> OCR + 设备检测 + 连线追踪 + 多模态语义校验
  -> 统一拓扑 Graph JSON
  -> 人工校正与置信度复核
  -> 场景编译
  -> Containerlab/Docker/VM/物理设备适配器
  -> 部署、健康检查与结果回传
```

详细能力边界、模块拆分、版本路线和验收标准见 [docs/PRODUCT_BASELINE.md](docs/PRODUCT_BASELINE.md)。统一拓扑中间表示见 [topology-schema/topology.schema.json](topology-schema/topology.schema.json)。

任何自动生成环境默认关闭互联网出口并禁止桥接生产网；部署真实厂商镜像、Windows 虚机或物理 PLC 时，必须由资源适配器检查镜像授权、资源可用性和隔离策略。

# 厂域镜像 Demo

该 Demo 演示从工厂拓扑图到可部署网络配置的最小闭环：

1. 上传 PNG、JPEG、WebP 或 SVG 拓扑图。
2. 使用浏览器端几何特征生成候选设备和链路。
3. 在右侧校正设备类型、IP、安全区域和运行模板。
4. 导出统一拓扑 JSON 或 Containerlab YAML。
5. 在隔离的 Linux/Docker 测试主机上部署真实网络命名空间和 veth 链路。

## 本地查看

直接打开 `dist/index.html`，或在 `dist` 目录启动任意静态文件服务器。

## 部署示例环境

需要 Linux、Docker 和 Containerlab。确认测试主机未桥接生产网络后，在 PowerShell 中运行：

```powershell
.\scripts\deploy-demo.ps1
```

当前图片识别属于产品 Demo：能够生成可校对的候选拓扑，但不会声称从图片中准确恢复未标注的系统版本、端口配置、PLC 程序或工艺逻辑。

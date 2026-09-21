# ICS Basic Demo

一个仿照 Vulhub 场景目录组织方式的**安全工控靶场模板**。它用于验证 TopoRangeHub 导出的设备、区域和链路在 Docker 中的部署流程；不包含已知漏洞、攻击脚本、真实 PLC 固件或生产网络连接。

## 场景组成

| 服务 | 作用 | 可访问性 |
| --- | --- | --- |
| `hmi` | 只读 HMI 监控页面 | 宿主机 `127.0.0.1:18080` |
| `plc-simulator` | 返回静态、模拟的 PLC 状态 JSON | 仅 Docker 内部网络 |

`range-net` 设置为 `internal: true`，容器不能通过该网络访问互联网；HMI 端口仅绑定到本机回环地址，不会暴露到局域网。

## 启动

在本目录执行：

```powershell
docker compose up -d --build
```

访问 <http://127.0.0.1:18080> 查看 HMI 页面。检查状态：

```powershell
docker compose ps
docker compose logs --tail 50
```

## 停止和清理

```powershell
docker compose down
```

该命令只移除此模板创建的容器与网络，不会影响 TopoRangeHub 主服务。若需要同时删除此模板创建的匿名数据卷，再额外使用 `docker compose down -v`。

## 与拓扑工程的关系

这是首个手工基线模板。后续的“场景编译器”应把审核过的拓扑 JSON 映射为同样的目录结构：每台设备对应一个明确的模拟服务/镜像，每条链路对应隔离网络策略，并始终要求人工审核后部署。

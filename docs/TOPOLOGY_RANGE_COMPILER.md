# 拓扑驱动虚拟靶场编译器

TopoRangeHub 的靶场不是固定水厂或业务页面。它使用用户上传图片识别并人工审核后的统一拓扑 JSON，生成一个可在隔离 Linux 主机用 Containerlab 部署的虚拟网络。

## 编译流程

```text
拓扑图片 → GLM → 矢量拓扑审核 → 导出 topology.json
                                   ↓
                         range_compiler.py
                                   ↓
             clab.yml + inventory.json + DEPLOY.md
                                   ↓
                  隔离 Linux/Containerlab 靶场主机
```

## 前置条件

- `review.status` 必须为 `approved`。
- `isolation.production_bridge` 与 `isolation.internet_egress` 必须均为 `false`。
- 只在专用 Linux 靶场主机安装并运行 Containerlab；不要在生产网、办公网或连接真实 PLC 的主机执行。

## 使用

```powershell
python backend\range_compiler.py examples\factory-demo.topology.json --output artifacts\range-packages\factory-demo
```

输出包中的 `clab.yml` 描述了真实的容器网络节点与点对点链路；`inventory.json` 将矢量图节点映射到容器、区域和设备模板。复制该目录到隔离 Linux 主机后：

```bash
containerlab deploy --topo clab.yml
containerlab inspect --topo clab.yml
containerlab destroy --topo clab.yml
```

首版使用 `alpine:3.20` 通用 Linux 节点，并为工作站、服务器、防火墙、交换机与 PLC 分配不同模板标识。下一阶段为经审核的节点模板绑定服务镜像、路由和防火墙规则；不会自动部署真实厂商固件、物理 PLC 或生产网络连接。
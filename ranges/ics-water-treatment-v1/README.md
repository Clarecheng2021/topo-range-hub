# 水处理操作训练场 v1

这是一个可实际操作的、本机 Docker 工控训练场景：HMI 页面经 Nginx 反向代理调用 PLC 过程模拟器，操作员可以启动/停止进水泵、观察液位动态变化、处理高低液位告警，并查看持续保存的操作事件。

> 所有标签、液位、告警和控制命令均为模拟数据。该场景没有真实 PLC 驱动、Modbus/S7/OPC UA 服务、生产网卡或互联网暴露端口。

## 架构

```text
浏览器（仅 127.0.0.1:18082）
          │
       HMI / Nginx
          │  range-net（internal）
     PLC process simulator
          │
     Docker volume（保存训练状态）
```

PLC 模拟器不发布宿主机端口；HMI 仅绑定回环地址。不要把 `18082` 改为 `0.0.0.0`，除非由隔离实验网络的管理员明确批准。

## 启动

```powershell
Set-Location 'E:\projects\topo-range-hub\ranges\ics-water-treatment-v1'
docker compose up -d --build
docker compose ps
```

打开 <http://127.0.0.1:18082>。

## 建议训练任务

1. 初始液位为约 58%，进水泵停止，液位会缓慢下降。
2. 在液位低于 25% 前启动进水泵，将液位恢复至 40%–80%。
3. 液位达到 85% 会产生高液位告警；停止泵并点击“确认告警”。
4. 使用“复位场景”回到初始状态；状态数据保存在 `plc-data` 卷，重启容器不会清空。

## 健康检查与停止

```powershell
curl.exe http://127.0.0.1:18082/health
docker compose logs --tail 80
docker compose down
```

若要清空模拟器历史状态并从头开始，执行：

```powershell
docker compose down -v
```
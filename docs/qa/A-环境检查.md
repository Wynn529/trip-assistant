# A 工作副本与环境检查

负责人：A（姓名待补）  
执行方：Codex 辅助执行；A 本人复现未做  
基线：文斓前期 `前期工作.zip`；暂无 Git 提交号  
最近更新：2026-10-28（北京时间）  
AI 辅助用途：解压和复制前期文件、逐文件哈希核对、运行导入与数据读取检查、记录实际输出。

本文件保留第一步环境检查的历史记录；A-1.1业务实现和44项离线测试结果见 `docs/modules/智能体.md` 与 `docs/evidence/agent-checks-latest.json`，下文“未测”指当时尚未执行的项目。

## 工作副本检查

输入：根目录 `前期工作.zip`。

操作：解压到 `前期工作/`；把其中 `travel_agent/` 的源码和数据复制到根目录同名工作目录，跳过 Python 缓存；用 PowerShell `Get-FileHash -Algorithm SHA256` 逐文件核对；对原压缩包进行操作前后哈希核对。

实际输出：

```text
工作副本文件数：15；逐文件 SHA256 一致
原始 ZIP SHA256：AE6BB8EDB0399021BA81862EE7F8C9982921CA07497E92EBF2C13AC370983BB7
原始 ZIP 未改变
```

状态：通过（只针对文件复制一致性）。

证据路径：`docs/qa/A-环境检查.md`（本次命令实际输出转录）。

## Python 导入和数据读取

环境：Windows、PowerShell；`python.exe` 路径为 `C:\Python314\python.exe`；版本 Python 3.14.6。

工作目录：项目根目录。

命令：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python -B -c "import sys; from travel_agent import TravelAgent; from travel_agent.contracts import TripRequest, WeatherContext, AgentResponse; from travel_agent.rules.planner import load_chengdu_data; print('Python:', sys.version.split()[0]); print('IMPORT_OK:', TravelAgent.__module__ + '.' + TravelAgent.__name__); print('CONTRACTS_OK:', ', '.join(t.__name__ for t in (TripRequest, WeatherContext, AgentResponse))); data = load_chengdu_data(); print('DATA_OK:', data['city'], 'activities=' + str(len(data['activities']))); print('NETWORK_CALLS: none'); print('SCOPE: import and data loading only')"
```

实际输出：

```text
Python: 3.14.6
IMPORT_OK: travel_agent.service.TravelAgent
CONTRACTS_OK: TripRequest, WeatherContext, AgentResponse
DATA_OK: 成都 activities=9
NETWORK_CALLS: none
SCOPE: import and data loading only
```

退出码：0。

状态：通过（只针对导入和数据读取）。

证据路径：`docs/qa/A-环境检查.md`（本次命令实际输出转录）。

未调用模型或天气接口，未执行 `TravelAgent.turn()`，未验证 Streamlit 启动，未运行 pytest。上述检查不能证明完整应用或 A 模块业务通过。

## 本人复现与签收

操作人：待补。本人复现状态：未做。C/文斓签收状态：待验收。

# 足球球迷问答 MVP

这是一个基于 LangChain 的足球球迷问答助手 MVP，面向赛前/赛后信息理解场景。它会围绕球队状态、伤病停赛、预计首发、关键球员、战术看点、近期表现和历史交锋检索资料，并用中文生成结构化回答。

本项目不是足彩或投注工具，不提供投注建议、盘口分析或赔率推荐。

## 功能

- FastAPI 接口：`POST /ask`
- LangChain + `langchain-openai` 调用 LLM
- DuckDuckGo 免费搜索层
- `requests` + `BeautifulSoup` 网页正文抓取和清洗
- JSON 本地 TTL 缓存，默认 6 小时
- Pydantic 结构化输出
- 搜索失败、网页抓取失败或 LLM 不可用时尽量降级返回清晰说明

## 项目结构

```text
football_fan_agent/
  app/
    main.py
    agent.py
    prompts.py
    schemas.py
    tools/
      duckduckgo.py
      webpage.py
    services/
      query_builder.py
      cache.py
      extractor.py
  .env.example
  requirements.txt
  README.md
```

## 安装

```bash
cd football_fan_agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 环境变量

你已经把用于接入 LLM 的 `.env` 放在工作区根目录，应用会自动尝试读取：

- `football_fan_agent/.env`
- 工作区根目录 `.env`
- 当前运行目录 `.env`

可参考 `.env.example`：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
FOOTBALL_AGENT_CACHE_PATH=.cache/football_agent_cache.json
FOOTBALL_AGENT_CACHE_TTL_SECONDS=21600
FOOTBALL_AGENT_MAX_SEARCH_RESULTS=5
FOOTBALL_AGENT_FETCH_TOP_N=5
LLM_CONNECT_TIMEOUT_SECONDS=15
SEARXNG_BASE_URL=
```

如果你已经使用下面这组变量名，也可以直接运行，无需改 `.env`：

```env
LLM_API_KEY=your_openai_compatible_api_key_here
LLM_MODEL_ID=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
```

可选搜索引擎：

```env
SEARXNG_BASE_URL=http://127.0.0.1:8080
```

配置后会优先调用 SearXNG JSON API，失败或无结果时再回退到 DDGS。

## 运行 FastAPI

Windows PowerShell 推荐直接运行：

```powershell
cd football_fan_agent
.\run_server.ps1
```

然后打开：

```text
http://127.0.0.1:8000
```

首页提供自由输入框，可以直接输入任意足球问题。

也可以手动运行：

```bash
cd football_fan_agent
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

## 命令行自由输入

如果你只想在终端里使用，推荐这个方式：

```powershell
cd football_fan_agent
.\run_cli.ps1
```

启动后直接输入问题，例如：

```text
阿森纳对拜仁这场怎么看？
```

终端会显示：

- 是否读到 LLM API key
- 当前模型和 Base URL
- 可选的 LLM 连接测试结果
- 每次提问后的后端流程进度：问题识别、搜索、网页抓取、合并材料、LLM 生成

## 调用示例

```bash
curl -X POST "http://127.0.0.1:8000/ask" ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"阿森纳对拜仁这场怎么看？\"}"
```

响应会包含：

```json
{
  "short_answer": "...",
  "match": "...",
  "teams": ["Arsenal", "Bayern Munich"],
  "competition": "...",
  "confirmed_facts": [],
  "likely_but_uncertain": [],
  "team_a_strengths": [],
  "team_a_concerns": [],
  "team_b_strengths": [],
  "team_b_concerns": [],
  "key_players": [],
  "tactical_focus": [],
  "likely_game_flow": "...",
  "fan_takeaway": "...",
  "sources": [],
  "uncertainty_note": "..."
}
```

## 注意事项

- 这是球迷信息问答助手，不提供投注建议。
- DuckDuckGo 结果质量和网页可抓取性会影响回答质量。
- 预计首发、伤病恢复、赛前训练消息通常有不确定性，回答会尽量区分已确认信息和媒体推测。
- 如果外部搜索或网页抓取失败，服务不会直接崩溃，会在 `uncertainty_note` 或来源信息中说明。

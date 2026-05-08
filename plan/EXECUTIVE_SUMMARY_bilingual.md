# Executive Summary — Investment Intelligence Center (IIC) v2.1
# 执行摘要 — 投资情报中心 (IIC) v2.1

> Companion to: `PLAN_v2.1_Investment_Intelligence_Center.md`
> 配套文件：`PLAN_v2.1_Investment_Intelligence_Center.md`
> Date / 日期: 2026-05-06
> What changed vs v2.0: Linux mini-PC default (no NAS today, NAS-ready for tomorrow); WeChat-first push.
> 与 v2.0 相比的变更：默认 Linux 迷你主机（暂不配 NAS，但路径设计已为未来 NAS 迁移做准备）；推送通道改为微信优先。

---

## English

### Why this version exists

The original Intelligence Center (v1.1, April 2026) was a single-purpose news and macro dashboard for one user. Version 2.x turns it into the news desk of a much larger system: a personal, always-on, **agentic investment-advisory team** running on a home box. The Intelligence Center is no longer the product. It is one agent in a fleet. Version 2.1 finalizes the deployment story: a **single Linux mini-PC** runs the entire stack, with **WeChat** as the push channel, and a clean **NAS-ready** storage layout so that adding a NAS later is a one-evening migration.

### What the system is

IIC v2.1 mimics a small investment shop. A team of specialist AI agents collaborates and competes:

1. **Intelligence Agent** — collects news, macro indicators, filings, and market drivers from APIs and open sources, ranks them, and emits two outputs: a visual dashboard plus a hourly/morning push brief delivered to the user's WeChat, and a structured, agent-readable digest used by the rest of the fleet.
2. **Fundamental Analysis Agent** — reads SEC, HKEX, and A-share filings, runs lightweight valuations, and emits stock-level recommendations with target price, time horizon, and max drawdown.
3. **Quant Trading Agent** — runs a transparent factor library (momentum, mean reversion, vol risk premium, PEAD, insider clusters, sector strength, crypto basis, FX carry) and emits signal-driven recommendations.
4. **Persona Agents** — style-mimicking strategists inspired by public writings of named investors: Jim Rogers, Warren Buffett, George Soros, Stanley Druckenmiller, Cathie Wood, Ray Dalio, Michael Burry, plus an anonymous retail-degen persona. Each is a prompt + bias-vector + private memory.
5. **Backtesting Agent** — runs continuously in the background. Every recommendation produced by an advisory agent opens a virtual position immediately. The agent paper-trades, marks-to-market, evaluates wins, losses, drawdowns, and feeds results back to the originating agent so it can self-improve. A live leaderboard ranks all advisory agents.
6. **Secretary Agent** — a chatbot interface and progress monitor. Composes the morning brief, answers questions in plain language (English or Chinese), and explains the system to non-technical family members. Reachable via web UI **and via WeChat conversation**.

### What is different from v1.1 → v2.0 → v2.1

- **Agentic workflow, not a single tool.** Six canonical agent roles, one orchestrator, one immutable advice ledger.
- **API-first, hardware-light.** Replaces local-GPU LLMs with **DeepSeek v4 Pro + Flash** API. Pro handles synthesis and reasoning; Flash handles bulk ingest, translation, narration, and chat.
- **Self-grading.** Every recommendation is paper-traded the moment it is published. Performance is attributed per agent and surfaced as a leaderboard.
- **Suggestion-only.** No real-money trading. Outputs include ticker, price band, time horizon, target band, stop-loss, and sizing hint.
- **Linux-only host (v2.1).** Ubuntu 24.04 LTS Server (or Debian 12). Native Docker, no VM tax, `systemd` keeps services up across reboots, `unattended-upgrades` keeps the box patched.
- **WeChat push (v2.1).** WeCom group bot for outbound briefs and alerts; WeCom self-built app for inbound chat with the Secretary; Server酱 fallback; ntfy + email as backups.
- **NAS-ready (v2.1).** All persistent state lives under `/srv/iic/<service>` so adding a NAS later means: stop containers → rsync → `mount -t nfs` → start containers. Compose file unchanged.

### Hardware — Linux mini-PC default

The home box is an orchestration host, not a model host. CPU, RAM, NVMe, and 24×7 reliability matter; a GPU does not.

- **Tier 0 — Try before you buy ($0–$200).** Repurpose any existing PC with ≥ 16 GB RAM. Add a UPS. Phase 0–1 prototype only.
- **Tier 1 — Used business mini PC ($200–$450). ⭐ best value.** HP EliteDesk 800 Mini, Dell OptiPlex Micro, Lenovo ThinkCentre Tiny — all 32 GB DDR4/5, 1 TB NVMe, vPro for remote management. Power ~7 W idle. Built for 24×7 fleets.
- **Tier 2 — New consumer mini PC ($650–$900). ⭐ recommended for Ziwei.** Beelink SER8 (Ryzen 7 8845HS, 32 GB DDR5, 1 TB NVMe, dual NVMe slots, 2 × 2.5 GbE), ~$700. Or Minisforum UM870. Power ~10 W idle. 96 GB RAM ceiling, room to add a small local model later.
- **Tier 3 — Polished prosumer ($900–$1,400).** Intel NUC 13 Pro, ASUS NUC 14 Pro, Framework Desktop. Better warranty and firmware refinement.
- **Tier 4 — DIY mini-ITX ($900–$1,500).** Ryzen 7 8700G + 32 GB ECC + Mini-ITX. Full upgrade path; can drop a single-slot GPU later.
- **Tier 5 — Workstation hybrid ($2,500+).** Only if you intend to leave API-first and host a local model.

**Recommended for v2.1 launch: Beelink SER8, $700, plus a $110 external 4 TB USB-C HDD for backups, plus a $120 UPS — total ~$930.** Ubuntu 24.04 LTS Server, ~10 W idle, fits in a drawer.

**Future NAS upgrade.** Synology DS923+ (~$600 diskless) or QNAP TS-464 (~$650) populated with 2 × 8 TB IronWolf in mirror. NFS-mount `/volume1/iic` at `/srv/iic` on the mini PC. Migration is one evening.

### LLM allocation — DeepSeek v4 Pro vs Flash

- **Pro** for the orchestrator's plan, the intelligence synthesis, fundamental valuation, persona reasoning, and "explain deeply" answers.
- **Flash** for ingest, translation, sentiment, factor narration, default chat, post-trade narrative.
- Cost envelope: **≤ $90/month** at sustained load; total infrastructure (data feeds + push + backups) **≤ $160/month**.
- Fallback chain: Pro → Anthropic Claude Sonnet 4.6; Flash → Groq Llama-3.3-70B.

### Push notifications — WeChat first

- **Primary outbound: WeCom (企业微信) group bot webhook.** Free, supports markdown, no rate-limit issues at our volume. Used for morning brief, alerts, fill notifications.
- **Primary inbound: WeCom self-built app + OAuth callback.** Two-way chat with the Secretary, lives inside 企业微信.
- **Fallback: Server酱 Turbo (sct.ftqq.com).** Pushes to your personal WeChat through the 服务号 "Server酱". ¥18/year.
- **Backups: ntfy + SMTP email.** For when WeChat is unreachable.
- Telegram remains an *ingest* source (read-only public channels) but is no longer a push target.

### Implementation plan — eight phases, ~16 weeks part-time

0. Foundations — Ubuntu 24.04 LTS Server hardened, Docker, NATS, Postgres+TimescaleDB, ChromaDB, MinIO, Grafana+Loki+Prometheus+node-exporter+cadvisor, CI, restic backups to MinIO + Backblaze B2.
1. Intelligence Agent MVP — fork WorldMonitor, 90 verified feeds, **WeChat brief** delivery.
2. Data Lake & Market Pipeline — OHLCV, fundamentals, factor matrix, PIT-correctness tests.
3. Fundamental Agent — filings, valuation, watchlist of 50 names.
4. Quant Agent — 8-factor library, regime detector, position sizing.
5. Persona Fleet — Rogers, Buffett, Soros, Druckenmiller live with disclaimer-validator.
6. Backtesting Engine — forward paper trading, attribution, leaderboard, feedback events.
7. Secretary + Chatbot UI — web chat, **WeChat conversational interface**, scheduled briefs, family-friendly tone.
8. Production hardening — eval harness, observability, DR drill, security review, **NAS-migration script tested in dry-run**.

### Success metrics

- WeChat morning brief delivered ≥ 95% of trading days within 5 min of schedule.
- ≥ 30% of recommendations contradict another agent (diversity of thought).
- ≥ 2 of 8 agents beat the smart-passive benchmark over 6 months on paper P&L.
- All-in monthly cost ≤ $160.
- A non-technical family member can ask the WeChat chatbot a question and understand the answer.
- Disaster recovery from cold backup in < 60 min.
- Mini PC uptime ≥ 99.5% over a rolling 30 days.

### Disclaimer

IIC is a personal research system. **It is not a registered investment advisor.** All outputs carry the IIC disclaimer: *"For personal research only. Not investment advice."* Persona agents are stylized, prompt-driven mimicry inspired by public writings; they never claim to be the real persons.

---

## 中文 (Chinese)

### 为什么需要 v2.1

最初的「情报中心」(v1.1，2026 年 4 月) 是一个单一用途的新闻与宏观看板，仅服务一位用户。v2.x 将其升级为更大系统中的「新闻情报台」：一个本地常驻、由智能体协作组成的**个人投资顾问团队**。情报中心不再是终点，而是舰队中的一员。**v2.1 进一步收敛部署方案：整套系统跑在一台 Linux 迷你主机上，推送通道全部走微信，存储路径预留 NAS 接入位**——未来加 NAS 就是一晚上的迁移工作。

### 系统是什么

IIC v2.1 模仿一家小型投资公司，由多个专精的 AI 智能体协同与竞争：

1. **情报智能体（Intelligence Agent）** — 通过 API 与公开源采集新闻、宏观指标、公司公告、市场驱动因子，进行排序与筛选，输出两份产品：①面向用户的可视化交互看板 + **通过微信推送**的每小时／晨间简报；②面向其他智能体的结构化摘要。
2. **基本面分析智能体（Fundamental Agent）** — 阅读美股 (EDGAR)、港股 (HKEX)、A 股的财报与公告，跑轻量化估值（DCF、可比公司、EV/EBITDA），输出**股票层级**的建议（带目标价、持仓时长、最大回撤）。
3. **量化交易智能体（Quant Agent）** — 运行透明因子库（动量、均值回归、波动率风险溢价、盈利后漂移 PEAD、内部人买入聚集、行业相对强弱、加密货币 basis、外汇 carry），输出量化信号。
4. **人格智能体（Persona Agents）** — 受公开著作启发、模仿名家投资风格的策略师：吉姆·罗杰斯、巴菲特、索罗斯、德鲁肯米勒、凯西·伍德、达里奥、麦克·伯里，以及一名匿名的「散户狂热者」人格。每位人格 = prompt + 偏好向量 + 专属记忆。
5. **回测智能体（Backtesting Agent）** — 永远在后台运行。每一条投资建议发布的瞬间，立即开仓虚拟头寸，按真实行情盯市，评估盈亏、胜率、回撤，并把结果反哺回提建议的智能体，让其自我优化。一个**实时榜单**显示所有顾问智能体的表现。
6. **秘书智能体（Secretary Agent）** — 聊天界面 + 进度监控。撰写晨间简报，用通俗语言（中文或英文）回答问题，向非技术背景的家人解释整套系统。可通过网页 UI **以及微信对话**直接交互。

### v1.1 → v2.0 → v2.1 的关键差异

- **智能体工作流，而非单一工具。** 六种规范化的智能体角色 + 一个调度器 + 一份不可变的「建议总账」。
- **API 优先，硬件轻量化。** 用 **DeepSeek v4 Pro + Flash** API 替代本地 GPU 模型。
- **自评分。** 每条建议在发布瞬间即开始模拟交易，业绩按智能体归因，并在榜单上展示。
- **只给建议，不下单。** 系统不接券商，不动钱。
- **Linux 单机宿主（v2.1）。** Ubuntu 24.04 LTS Server（或 Debian 12）。Docker 原生运行，无虚拟机损耗，`systemd` 自启，`unattended-upgrades` 自动安全更新。
- **微信推送（v2.1）。** 出向：企业微信群机器人 webhook 推送早报与告警；入向：企业微信自建应用 + OAuth 回调，与秘书智能体进行会话；备用：Server酱；兜底：ntfy + 邮件。
- **预留 NAS 接入（v2.1）。** 所有持久化数据放在 `/srv/iic/<service>`。未来加 NAS 时：停容器 → rsync → NFS 挂载 → 起容器，compose 文件不动。

### 硬件 — 默认 Linux 迷你主机

家里这台机器是**调度宿主**，不是模型宿主。CPU、内存、NVMe、长期稳定性才重要，GPU 并不需要。

- **Tier 0 — 先用旧机器试试（$0–$200）。** 任何 ≥ 16 GB 内存的旧 PC/笔记本都行，加一个 UPS。仅适合 Phase 0–1 原型阶段。
- **Tier 1 — 二手商用迷你机（$200–$450）。⭐ 性价比之王。** 惠普 EliteDesk 800 Mini、戴尔 OptiPlex Micro、联想 ThinkCentre Tiny 等企业淘汰机，32 GB 内存 + 1 TB NVMe，自带 vPro 远程管理。空载约 7 W。本就为 7×24 设计。
- **Tier 2 — 全新消费级迷你机（$650–$900）。⭐ 推荐给 Ziwei。** Beelink SER8（Ryzen 7 8845HS，32 GB DDR5，1 TB NVMe，双 M.2，双 2.5 GbE），约 $700；或 Minisforum UM870。空载约 10 W。内存上限 96 GB，未来想跑本地小模型也有余地。
- **Tier 3 — 精品准专业级（$900–$1,400）。** Intel NUC 13 Pro、ASUS NUC 14 Pro、Framework Desktop。质保更好，固件更精致。
- **Tier 4 — 自组 mini-ITX（$900–$1,500）。** Ryzen 7 8700G + 32 GB ECC + 紧凑型机箱。可任意升级，未来可加单槽 GPU。
- **Tier 5 — 工作站混合方案（$2,500+）。** 只有在你打算放弃 API 优先、把模型搬回本地时才需要。

**v2.1 启动推荐：Beelink SER8（$700）+ 4 TB USB-C 移动硬盘（$110，作 `/srv/iic/backup`）+ UPS（$120），合计约 $930。** Ubuntu 24.04 LTS Server，空载约 10 W，可塞抽屉里。

**未来 NAS 升级路径。** 群晖 DS923+（约 $600 裸机）或威联通 TS-464（约 $650），插 2 × 8 TB IronWolf 做镜像，把 `/volume1/iic` 通过 NFS 挂到迷你主机的 `/srv/iic`。一晚上完成迁移。

### LLM 分配 — DeepSeek v4 Pro 与 Flash

- **Pro** 用于：调度器的任务规划、情报综合、基本面估值、人格推理、深度解释问答。
- **Flash** 用于：摄取、翻译、情感分类、因子叙事、默认聊天、交易后复盘。
- 成本目标：**LLM ≤ $90 / 月**；含数据源、推送、备份的总基础设施成本 **≤ $160 / 月**。
- 容灾链路：Pro → Anthropic Claude Sonnet 4.6；Flash → Groq Llama-3.3-70B。

### 推送通道 — 微信优先

- **主出向：企业微信群机器人 webhook。** 免费，支持 markdown，本系统流量远低于限速。早报、告警、虚拟成交都走它。
- **主入向：企业微信「自建应用」+ OAuth 回调。** 在企业微信里与秘书智能体双向对话。
- **备用：Server酱 Turbo（sct.ftqq.com）。** 通过服务号「Server酱」推送到你个人微信。¥18 / 年。
- **兜底：ntfy + SMTP 邮件。** 当微信线路异常时使用。
- Telegram 仍作**摄取**信源（只读公开频道），不再是推送目的地。

### 实施计划 — 八阶段，约 16 周（业余时间）

0. **基础设施** — Ubuntu 24.04 LTS Server 加固完成，Docker、NATS JetStream、Postgres + TimescaleDB、ChromaDB、MinIO、Grafana + Loki + Prometheus + node-exporter + cadvisor、CI 链路；restic 备份到本机 MinIO + Backblaze B2 异地。
1. **情报智能体 MVP** — 从 WorldMonitor 分叉，启用 90 个 Wave-1 已验证信源，**微信简报**正式上线。
2. **数据湖与行情管道** — OHLCV、基本面快照、因子矩阵、严格的 point-in-time 测试。
3. **基本面智能体** — 公告摄取与分块、估值引擎、50 只观察名单。
4. **量化智能体** — 8 因子库、宏观状态识别器、风险与仓位控制。
5. **人格舰队** — 罗杰斯／巴菲特／索罗斯／德鲁肯米勒上线，免责声明强制校验。
6. **回测引擎** — 实时模拟交易、归因、榜单、反馈事件。
7. **秘书与聊天 UI** — 网页聊天 + **微信会话**接入、推送、家庭友好的语气调档。
8. **生产化加固** — 评测套件、可观测性、灾难恢复演练、安全评审、**NAS 迁移脚本干跑测试**。

### 成功指标

- 微信晨间简报在 ≥ 95% 的交易日按时送达。
- ≥ 30% 的建议与其他智能体存在分歧（思想多样性）。
- 6 个月内，至少 2 个智能体在模拟盘上跑赢「智能被动」基准。
- 月度总成本 ≤ $160。
- 一位非技术背景的家人能在微信里就「今天有什么值得关注的」与机器人对话并听懂回答。
- 冷备恢复演练 < 60 分钟。
- 迷你主机滚动 30 天可用率 ≥ 99.5%。

### 免责声明

IIC 是一套个人研究系统，**并非注册投资顾问**。所有输出均带「仅供个人研究，不构成投资建议」的声明。人格智能体仅是基于公开著作的风格化模仿，绝不会自称是真人本人。

---

## TL;DR (one paragraph each)

**EN.** IIC v2.1 is a personal, always-on, agentic investment-advisory system. Six AI agents (intelligence, fundamental, quant, personas, backtester, secretary) collaborate and compete, all powered by DeepSeek v4 Pro + Flash via API. It produces concrete stock-level suggestions with price bands and time horizons but does not trade. A backtester paper-trades every suggestion in real time and ranks the agents on a live leaderboard. The whole stack runs 24×7 on a single Linux mini-PC (recommended: Beelink SER8 with Ubuntu 24.04 LTS Server, ~$700 hardware) and pushes briefs to the user via WeChat. All persistent state lives under `/srv/iic` so adding a NAS later is a one-evening migration. Eight phases over about 16 part-time weeks, ≤ $160/month in services.

**中文。** IIC v2.1 是一套常驻在家的个人智能投资顾问系统。六个 AI 智能体（情报、基本面、量化、人格、回测、秘书）协同与竞争，统一通过 DeepSeek v4 Pro / Flash API 提供算力。系统输出具体到股票层级的建议（价格区间、时间窗口、目标价、止损），但**不下单交易**。回测智能体在建议发布瞬间开仓虚拟头寸，并在实时榜单上对所有顾问智能体进行排名与反馈。整套服务运行在**一台 Linux 迷你主机**上（推荐 Beelink SER8 + Ubuntu 24.04 LTS Server，硬件约 $700），简报和告警**通过微信推送**给用户。所有持久化数据放在 `/srv/iic`，未来加 NAS 只需一晚上完成 NFS 迁移。八阶段、约 16 周业余时间，月度服务费 ≤ $160。

# 智能律询通 · 端到端 Demo

> 依据《智能律询通》项目 PPT 的**端到端部署**与**工作流分析**做的一个可运行演示。
> C 端 AI 法律咨询 → 会话落库 → B 端意向客户线索，全链路闭环。

---

## 一、快速开始

### 方式 A：双击启动（推荐）

双击项目根目录的 **`启动Demo.bat`**，浏览器会自动打开 `http://127.0.0.1:8000`。

### 方式 B：命令行

```bash
cd legalassist-demo
python app/server.py --port 8000 --open
```

> **零依赖也能跑**：核心链路只用 Python 3 标准库，`pip install` 不是必需的。
> 若装好了向量依赖并下载了 BGE 模型（见第五节），会自动启用**语义向量检索**；
> 没装则自动降级为纯词面检索，服务照常可用。已在 Python 3.12 上验证通过。

### 验证链路是否正常

```bash
python tools/smoke_test.py      # 端到端链路（4 轮咨询 → B 端线索）
python tools/eval_retrieval.py  # 检索质量评测（44 题标注集，含三通道对比）
```

`smoke_test.py` 会模拟一次 4 轮的完整咨询，并打印每一步的工作流时序和最终的 B 端线索分析。

---

## 二、演示脚本（3 分钟讲完）

界面为模拟手机壳的移动端交互：**首页 → 法律咨询（C 端）→ 客户详情（意向分析）→ 律师工作台（B 端）**，
底部标签栏与四张交互稿一致。

1. **首页** → 点「进入咨询」进入 C 端。点快捷标签「劳动纠纷」（或自己输入），
   AI 回答以结构化卡片呈现：`法律依据 → 证据清单 → 维权路径 → 风险提示`，附命中法条。
2. **看工作流时序**：聊天页右上角「···」→「工作流时序」，逐步展示
   `用户输入 → 意图识别 → 工具一 法条检索 → 工具二 案例匹配 → 工具三 风险评估 → 生成回答 → 风险提示`，
   每一步标注 **MoMA 路由到了哪个模型**（可在浮层内直接演示"简单意图走千问-Turbo、复杂回答走 DeepSeek-V3"）。
3. **继续追问 2~3 轮**（想问仲裁时效 → 表示想找律师）。观察线索评分同步上升。
4. **首页 → 「律师登录认证」**（演示环境直接点登录）→ 进入**律师工作台**：
   顶部三张统计卡（今日新增线索 / 高意向客户 / 案件类型分布）由真实线索实时计算，
   下方线索卡片带客户ID、案件标签、AI意向评级、咨询摘要；可切换「案件类型 / 意向等级 / 咨询时间」筛选。
5. **点「查看报告」**进入客户详情：咨询时间 / 纠纷类型 / 地域标签 / 客户意向四宫格，
   AI 意向分析报告（用户诉求 · 案件关键点 · 风险评估 · 意向判断）、建议跟进方向、
   可展开的原始咨询记录、添加跟进记录，底部「标记为已沟通」将其转入「客户」标签页。
6. **「我的」**：系统状态（知识库规模、模型路由配置、向量后端）、演示工具（生成演示线索 / 清空数据）。

> 无手工数据也能演示：首次打开「我的 → 生成演示线索」会通过**真实流水线**跑 12 条样例咨询
> （见 `app/data/demo_seed.json`），因此工作台的统计、评级、摘要全部是引擎真实产出，而非写死数字。

---

## 三、目录结构

```
legalassist-demo/
├── 启动Demo.bat              # 一键启动
├── README.md                 # 本文件
├── docs/
│   ├── 端到端部署与工作流分析.md   # PPT → 实现的逐条对照
│   └── 部署实施与迭代记录.md       # 实际部署顺序 · 验证方法 · 迭代闭环
├── app/
│   ├── server.py             # 接入层 + 服务层（标准库 HTTP 服务）
│   ├── engine/               # ===== AI 能力层 =====
│   │   ├── config.py         #   模型路由表 / 检索参数
│   │   ├── llm.py            #   MoMA 多模型智能路由
│   │   ├── nlu.py            #   意图识别 + 法律实体抽取
│   │   ├── embed.py          #   文本嵌入（ONNX BGE / API / hash 三级降级）
│   │   ├── vector_index.py   #   向量索引（numpy 余弦检索 + 磁盘缓存）
│   │   ├── rag.py            #   混合检索：稠密 + 词面，RRF 融合
│   │   ├── tools.py          #   Function Calling 三工具
│   │   ├── generator.py      #   Prompt 工程 + 三段式回答 + 记忆压缩
│   │   ├── lead.py           #   B 端意向评分与分析报告
│   │   ├── pipeline.py       #   端到端编排（五步流程 + trace）
│   │   ├── store.py          #   会话存储（数据层）
│   │   └── textutil.py       #   否定感知的中文匹配 + 字符二元组
│   ├── data/                 # ===== 数据层 =====
│   │   ├── law_kb.json       #   法条知识库（1037 条，含时效元数据）
│   │   ├── cases.json        #   案例库（8 条，虚构演示数据）
│   │   ├── demo_seed.json    #   演示线索数据集（12 条样例咨询，走真实流水线生成）
│   │   ├── models/           #   BGE-small-zh-v1.5 ONNX 权重（91MB，可选）
│   │   ├── index_cache/      #   向量索引缓存（自动生成）
│   │   ├── corpus_cache/     #   法条原文缓存（自动生成，可离线重建）
│   │   └── sessions/         #   会话落盘（运行时生成）
│   └── web/                  # ===== 接入层 =====
│       ├── index.html        #   手机壳容器 + 图标精灵（内联 SVG，无外部依赖）
│       ├── style.css         #   移动端设计系统（卡片 / 气泡 / 图表 / 浮层）
│       ├── app.js            #   内核：状态机 · 路由 · 接口 · 图表 · 回答解析
│       └── views.js          #   五个界面：首页 / 咨询 / 客户详情 / 工作台 / 我的
└── tools/
    ├── fetch_model.py        # 下载 BGE ONNX 模型（HF / hf-mirror 双镜像）
    ├── build_corpus.py       # 从公开法律仓库构建法条知识库
    ├── eval_retrieval.py     # 检索质量评测 + RRF 权重扫描
    ├── smoke_test.py         # 端到端冒烟测试
    └── dump_pptx.py          # 从 PPTX 抽取文本
```

### HTTP 接口一览

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 运行状态：模型模式、知识库规模、向量后端、索引 |
| GET | `/api/router/stats` | MoMA 路由调用统计（本次进程） |
| GET | `/api/leads` | B 端线索池，支持 `category` / `grade` / `status` 过滤 |
| GET | `/api/sessions` · `/api/session/<id>` | 会话列表 / 单会话详情（含完整对话记录） |
| POST | `/api/chat` | C 端咨询一轮（返回回答、法条引用、风险评估、工作流 trace） |
| POST | `/api/leads/analyze` | 强制重算某会话的意向分析 |
| POST | `/api/leads/status` | 跟进状态：待跟进 / 已联系 / 已转化 |
| POST | `/api/leads/note` | 保存跟进记录 |
| POST | `/api/demo/seed` | 生成演示线索（走真实流水线，可重复调用） |
| POST | `/api/admin/reset` | 清空全部演示数据 |

界面还支持深链直达：#/home · #/chat · #/workbench · #/customers · #/me · #/lead/<会话ID>，
讲演示时可以直接跳到某一屏，不用一路点过去。

---

## 四、PPT 设计 → 代码实现的对照

| PPT 设计 | 实现位置 | 说明 |
|---|---|---|
| 四层架构（接入/服务/AI/数据） | `web/` + `server.py` + `engine/` + `data/` | 目录结构即分层 |
| C 端五步咨询流程 | `engine/pipeline.py` | 每步产出一条 trace，前端实时渲染 |
| B 端意向客户分析 | `engine/lead.py` | 会话 → 结构化线索 + 分析报告 |
| MoMA 多模型路由 | `engine/llm.py` | 千问-Turbo / GLM-4 / DeepSeek-V3 三档位 |
| RAG 上下文动态注入 | `engine/rag.py` + `generator.build_prompt()` | 混合检索排序后拼入 Prompt |
| 向量库检索（策略②） | `engine/embed.py` + `engine/vector_index.py` | BGE 向量 + 余弦 Top-K，带磁盘缓存 |
| 混合检索 + 精排（第 13 页） | `engine/rag.py::_fuse()` | 稠密 + 词面双通道 RRF 融合 |
| 三段式结构化输出 | `generator.render_answer()` | 法律依据 → 证据清单 → 维权路径 |
| 多轮记忆管理（超 10 轮压缩） | `generator.compress_history()` | 会话摘要 + 关键事实沉淀 |
| 工具一 法条检索 | `tools.tool_search_statutes()` | 入参：案件类型 + 关键词 → Top-K |
| 工具二 案例匹配 | `tools.tool_match_cases()` | 触发词命中才调用 |
| 工具三 风险评估 | `tools.tool_assess_risk()` | 证据清单 + 规则引擎 → 等级与概率区间 |
| 意向评分 高/中/低 | `lead.score()` | 可解释因子加权，律所可调参 |
| 免责与风险提示 | `config.DISCLAIMER` + 每轮末尾 | 强制附加 |

---

## 五、检索层：从关键词到混合向量检索

这是本项目**从 Demo 走向可用**的关键一步。检索质量直接决定回答里引用的法条对不对。

### 5.1 架构

```
查询 ─┬─ 稠密通道：BGE-small-zh 向量 → 余弦相似度 Top-N ─┐
      └─ 词面通道：IDF 加权二元组 + 关键词 Top-N ────────┤
                                                      ├─ RRF 融合 → Top-K
                    案件类型（category）元数据先验 ──────┘
```

两条通道互补，缺一不可：

- **稠密通道**擅长同义改写——「没签合同」≈「未订立书面劳动合同」，
  「被开除」≈「用人单位解除劳动合同」。纯关键词匹配对这类口语化表达无能为力。
- **词面通道**擅长精确信号——法条号、专有名词（「竞业限制」「不安抗辩权」）、
  否定表达。这些恰恰是向量容易糊掉的地方。

用 **RRF（Reciprocal Rank Fusion）** 按*名次*而非分数融合，规避两路分数量纲
不可比的问题。

### 5.2 实测效果

44 题人工标注集（口语化提问 32 题 + 规范术语 12 题），Hit@K = 期望法条落在前 K 名：

| 通道 | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| 词面通道（≈ Phase 0 水平） | 47.7% | 61.4% | 0.544 |
| 稠密通道（BGE 向量） | 47.7% | 68.2% | 0.580 |
| **混合融合（本项目采用）** | **56.8%** | **68.2%** | **0.625** |

```bash
python tools/eval_retrieval.py            # 复现上表
python tools/eval_retrieval.py --sweep    # 扫描 RRF 通道权重
```

> 标注集规模有限（44 题），1~2 题的差异属噪声，这张表说明的是**趋势**而非精确排名。
> 明细会逐题打印未命中的问题，便于定位检索短板。

### 5.3 知识库构成（1037 条）

| 法律 | 条数 | 案件类型 |
|---|---|---|
| 民法典（总则/合同/婚姻家庭/侵权责任编） | 680 | contract / marriage |
| 劳动法 | 107 | labor |
| 劳动合同法 | 98 | labor |
| 工伤保险条例 | 67 | labor |
| 劳动争议调解仲裁法 | 54 | labor |
| 民间借贷司法解释 | 31 | loan |

法条正文取自公开法律文本仓库 `risshun/Chinese_Laws` 与 `LawRefBook/Laws`，
经 `tools/build_corpus.py` 解析成「条」级结构，并**补充了时效元数据**
（`status` 现行有效 / `effective_date` 施行日期），供风险提示环节判断法条是否仍然适用。

重新构建（可离线，源文件已缓存到 `data/corpus_cache/`）：

```bash
python tools/build_corpus.py              # 增量构建
python tools/build_corpus.py --refresh    # 强制重新下载源文件
```

### 5.4 启用真实语义检索（可选，约 115MB）

```bash
pip install onnxruntime tokenizers        # 一次性安装
python tools/fetch_model.py               # 下载 BGE-small-zh-v1.5（91MB，双镜像）
```

之后启动服务会自动加载模型并预热索引。首次启动需编码全部 1037 条法条
（约 20 秒），此后走磁盘缓存（毫秒级）。向量缓存以「语料指纹 + 后端 + 维度」
为 key，语料或模型一变就自动失效重建，不会出现新旧向量混用。

常用环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `LEGALASSIST_EMBED_MODE` | `auto` | `auto` / `onnx` / `api` / `hash` |
| `LEGALASSIST_HYBRID` | `1` | 置 `0` 关闭混合检索，退回词面通道 |
| `LEGALASSIST_DENSE_FLOOR` | `0.30` | 稠密通道相似度准入门槛 |
| `LEGALASSIST_RRF_WLEX` | `1.0` | RRF 词面通道权重 |

### 5.5 已知短板（诚实说明）

1. **合同编内部辨析难**。民法典合同编 576 条语义高度接近，「一物二卖」这类问题
   会被 597、643、629 等多条同时命中，Top-1 不稳定。
2. **跨法版本冲突未自动裁决**。例如劳动法第 82 条（旧的 60 日仲裁期限）已被
   劳动争议调解仲裁法第 27 条（1 年）取代，两条都与提问相关。系统会同时召回，
   但**不会自动判定新法优于旧法**——这是下一步要做的时效裁决逻辑。
3. **复合提问会被稀释**。「要花钱吗+多久内必须申请」这类多问题句，向量相似度
   被摊平，单条法条的排名会下滑。需要查询改写/分解（query decomposition）。
4. **口语化短查询向量区分度低**。仅「双倍工资」四个字时，全库余弦相似度挤在
   0.43~0.48 之间，靠词面通道才能拉开。这是小模型（24M 参数）的固有局限。

---

## 六、接入真实大模型

Demo 默认运行在 **`mock` 模式**：不联网，回答由本地规则引擎生成，
保证无 API Key 的环境也能完整跑通端到端链路。

切换到真实模型（MoMA / DeepSeek / 智谱 / 通义 都提供 OpenAI 兼容端点）：

```bash
# Windows CMD
set LEGALASSIST_LLM=openai-compatible
set LEGALASSIST_BASE_URL=https://your-moma-endpoint/v1
set LEGALASSIST_API_KEY=sk-xxxxxx
python app/server.py --port 8000

# Git Bash / Linux / macOS
export LEGALASSIST_LLM=openai-compatible
export LEGALASSIST_BASE_URL=https://your-moma-endpoint/v1
export LEGALASSIST_API_KEY=sk-xxxxxx
python app/server.py --port 8000
```

切换后：
- `engine/llm.py` 会把组装好的 Prompt 真实发往对应模型；
- 远程调用失败时**自动降级**回本地规则引擎，服务不中断；
- 「我的 → 系统状态」会显示当前接入模式与知识库规模。

模型档位映射在 `engine/config.py` 的 `MODEL_TIERS` 中，把 `model` 字段改成
MoMA 平台上的真实模型名即可。

---

## 七、演示数据声明

- **法条正文**取自公开法律文本仓库并做结构化处理，用于演示检索形态。
  正式法律事务请以[国家法律法规数据库](https://flk.npc.gov.cn/)发布的正式文本为准。
- **案例库全部为虚构样例**，案号、法院、当事人均为编造，
  仅用于展示检索链路，**不得作为法律依据引用**。
- **演示线索**（`app/data/demo_seed.json`）中的咨询问题是编写好的样例，
  但其分析结果——案件类型、意向评分、证据清单、跟进建议——均由引擎实时计算，
  时间戳回填到过去 0~9 天仅为了让「今日 / 近7日」统计具备分布。
- **意向评分权重、胜诉概率区间**为演示用启发式规则，非真实统计模型。
- 法条已标注**时效元数据**（现行有效 / 施行日期），但系统**不会自动裁决
  新旧法冲突**，引用前仍需人工核对。
- 本项目输出**不构成法律意见**。

生产环境需替换：案例库 → 中国裁判文书网/商业判例库；embedding → 更大规模的向量
模型与向量库；评分模型 → 基于真实转化数据训练的模型。

---

## 八、从 Demo 到生产：待替换清单

| 层 | Demo 实现 | 生产建议 |
|---|---|---|
| 接入层 | 浏览器单页 | 微信小程序 + 微信授权登录 + 消息推送 |
| 服务层 | `http.server` 单进程 | FastAPI / Spring Boot + Nginx，水平扩展 |
| AI 层 | BGE-small-zh（24M）+ numpy 暴力检索 | 换 `bge-m3`/`bge-large-zh` + pgvector/Milvus + Cross-Encoder 精排 |
| AI 层 | 本地规则引擎 | MoMA 真实模型调用 + Prompt 版本管理 |
| 检索质量 | 44 题标注集，Hit@1 56.8% | 千级标注集 + RAGAS 自动评测 + 定期回归 |
| 法条时效 | 元数据已标注，人工判断 | 新法优于旧法 / 特别法优于一般法的自动裁决 |
| 数据层 | JSON 文件 | PostgreSQL / MySQL + Redis 会话缓存 |
| 线索 CRM | JSON 落盘 | 客户表 + 跟进记录表 + 权限体系 |
| 评估 | 手工观察 | 自动化评测集：法条引用准确率 / 幻觉率 / 响应延迟 P95 |
| 合规 | 免责声明 | 律师执业合规审查、用户协议、个人信息保护（个保法） |

---

## 九、常见问题

**Q：`python` 命令报错 `Unable to create process`？**
这台机器上 `python` 指向了 Microsoft Store 的占位程序。请直接双击 `启动Demo.bat`，
或用完整路径：`"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" app/server.py`。

**Q：端口 8000 被占用？**
换成 `--port 8010`（或任意空闲端口）。

**Q：想清空 / 重建演示数据？**
「我的 → 演示工具 → 清空演示数据」，或手动删除 `app/data/sessions/` 目录。
想在空环境里快速铺满工作台，点「生成演示线索」（等价于 `POST /api/demo/seed`）——
它会清理上一次生成的演示线索后重建，不影响你真实咨询产生的会话。

**Q：没装 `onnxruntime`，会不会跑不起来？**
不会。`engine/embed.py` 有三级降级链：ONNX 模型 → API 嵌入 → hash 兜底，
任何一环缺失都自动往下走，服务始终可用。可以用 `/api/health` 看当前实际后端：

```bash
curl http://127.0.0.1:8000/api/health
# "embedder": {"backend": "onnx-bge-small-zh", "semantic": true, ...}
```

`"semantic": false` 说明当前在用 hash 兜底，检索**没有真实语义能力**，
只是把词面匹配搬进了向量空间——演示形态可用，但别当成向量检索的成果。

**Q：模型下载失败？**
`tools/fetch_model.py` 会依次尝试 huggingface.co 与 hf-mirror.com，支持断点续传。
若都失败，先确认网络，或手动把 5 个文件放进 `app/data/models/bge-small-zh-v1.5/`。


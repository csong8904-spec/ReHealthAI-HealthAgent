# 更新日志

[English](CHANGELOG.md) | **简体中文**

本文件记录项目的所有重要变更。

## [0.2.0] - 2026-10-18

内部实现完全重写。领域思路不变；实现、模型语义与打包方式都变了。

### 修复 — 阻断性问题

* `healthagent.engine.simulation_engine` 无法 import：它引用了一个不存在的 `get_intervention_plan()`。现在补上了方案注册表，每次调用返回新实例。
* `examples/*.py` 在 `from healthagent import SimulationEngine` 处失败；包现在导出了公共 API。
* `requirements.txt` 列了四个没被用到的包（numpy、pandas、click、rich），却漏了两个真正 import 的（`openai`、`python-dotenv`）。改为用 `pyproject.toml` 精确声明运行时依赖。
* `simulate.py` 在中文 Windows 默认控制台（GBK）下因 emoji 触发 `UnicodeEncodeError` 崩溃。
* `healthagent/run.py` 与 `api/routers/*` 写死了作者本机 Windows 路径；`patient_db/db.py` 写死了另一个本机路径。所有机器相关路径已移除，数据库路径改为 `REHEALTH_DB_PATH`，默认 `~/.rehealth`。
* FastAPI 应用无法从仓库根目录 import（`from routers import ...`），且没有任何启动文档。现在是 `api.main:app`，带 `api/__init__.py` 并已写入文档。
* README 宣传了并不存在的 `visualize.py`。现在它存在，有渲染测试（未安装 matplotlib 时跳过），并在 CI 中执行。

### 修复 — 模型 / 行为

* **缺失的反馈边**：依从性从不影响压力，导致高压力患者无论依从与否都会恶化。现在依从会降低压力目标，权重为方案有效性。
* **慢性压力重复计算**：生理模型使用绝对压力，惩罚了基线本就在该压力下测得的患者。现在只惩罚超出基线的那部分，所有效应量都相对患者自身基线。
* **锚定**：睡眠质量与 HRV 乘数在基线行为处取中性，因此零依从约等于零变化，而不是虚假改善。
* **优先级降级 bug**：`priority = max(priority, "medium")` 比较的是字符串，而 Python 中 `max("high", "medium") == "medium"`。现在优先级是 `IntEnum`；紧急日不会被降级，也不会被冷却吞掉。
* **头部指标**原先用「最后一天减基线」（单日噪声），现在改为末 14 天均值（`metric_window_days`）。
* **提醒疲劳**：任意滚动 30 天内最多 8 条提醒，并避免重复文案。
* LLM 调用预算现在真正生效：单次运行上限 `天数 + 5` 次请求（可用 `max_llm_calls` 覆盖），重试也计入。
* LLM 模式已对真实 DeepSeek API（`deepseek-chat`）验证：7 次调用、约 15 秒、约 3.1k token。模型的 `narrative` 与 `key_factor` 现在写入 `DailyState`，不再被丢弃。
* **部分依从不再被记为零分。** 实跑中模型每天都返回 `complied: false` 且 `compliance_quality: "partial"`（"完成了冥想，跳过了散步"），而 v0.2.0 把它算成 0% 依从、零生理效应。现在以 `compliance_quality` 为准：full = 1.0、partial = 0.6、none = 0.0，分数大于零即计为依从日。
* `LLMClient.usage_summary()` 累计报告 prompt/completion/total token，便于核算成本。
* `seed=None` 不再虚报可复现：只有「有种子且离线」才标记为可复现。
* `--days` 超出 1–730 现在给出 argparse 错误，而不是抛堆栈。
* `GET /api/patients/{id}/trend` 对不存在的患者返回 404（而不是 `200 {"error": ...}`）；`POST /api/patients` 同时返回 `id` 别名。
* 移除了最后一批未使用的 import 和 docstring 里的历史绝对路径；新增测试扫描源码树中的机器路径。

### 变更

* 四个「agent」按实际情况描述：确定性状态机，其中只有一个可选地调用 LLM。
* 显式的离线模式（`--offline`、`REHEALTH_OFFLINE`）让演示、测试与 CI 免费、快速且可复现。
* `SimulationResult` 新增 `mode`、`seed`、`reproducible`、`patient`、`intervention`、`baseline` 以及有文档的 `to_dict()` 结构。
* 依从性拆分为 `compliance_rate`（有依从的天数）、`full_compliance_rate`（1.0 分）与 `partial_compliance_rate`（0.6 分），便于汇报时区分「做完」和「做了一部分」。
* 患者模型：新增 `gender`、`occupation`、`wearable`、`habit_strength`、`social_support`；所有数值范围校验；`stress_level` 接受大小写不敏感的字符串。
* HTTP API：请求校验（`days` 1–365、临床字段边界）、可选的 `X-API-Key` 网关、非阻塞处理、CORS 白名单。
* 可选的 DeerFlow 封装（`healthagent/run.py`）不再包含本机路径，并返回明确的「非医疗建议」声明。

### 新增

* `tests/` — 83 个 pytest 测试，含剂量反应不变式。
* `.github/workflows/ci.yml` — Python 3.10/3.12 + 离线 CLI 冒烟测试。
* `pyproject.toml`、`CHANGELOG.md`、`.env.example` 覆盖所有变量。
* 双语文档：`README.md`（英文）与 `README.zh-CN.md`（简体中文），顶部互相链接；两个 CHANGELOG 亦然。
* 自动生成的 OpenAPI 文档（`/docs`）为中英双语：应用描述、分组标签、接口摘要、请求字段说明与响应说明均含英文 + 简体中文；`.env.example` 同样双语。

### 移除

* `artifacts/`（与本库无关的二进制资产）、`test.py`（没有任何断言）、`commit.sh`、`commit_msg.txt`、过期的 `requirements.txt` 与 `api/requirements.txt`。

## [0.1.0] - 2026-03-09

首个公开 demo，按文档无法运行。

# 数字口径核对（2026-11-05）

触发原因：仓库的卖点是"可验证"，同一份材料里同一个量出现两个值会直接摧毁这个主张。
本文逐条记录**哪个数是真的、依据是什么、谁被改**。凡属"口径不同"而非"算错"的，
保留两个数但强制加口径标签，读者不应再看到两个裸值。

核对方式一律为**从原始数据重算**，不采用"挑一个看起来合理的"。

---

## 汇总

| # | 文件 | 原值 | 判定 | 真值 / 处理 |
|---|---|---|---|---|
| 1 | `outputs/multisample-run.md` | "11 题 1–5/8" | **真错** | 9 题 1–5/8、2 题 7/8 |
| 2 | `outputs/first-run-memo.md` | directional 425 / 575 / 771 | 口径合法并存 | round 3 / 5 / 10，全部加轮次标签 |
| 3 | `outputs/first-run-memo.md` | 中位 VCI 0.934 与 0.969 | 口径合法并存 | round 3–7 为 0.934，round 10 为 0.969 |
| 4 | `outputs/first-run-memo.md` | 族数 16/20 与 17/20 | 口径合法并存 | round 3 为 16/20，round 5 起为 17/20 |
| 5 | `outputs/first-run-memo.md` | "10 接受 + 89 失败"（合计 99） | **真错** | 10 接受 + **90** 未接受（1 解析 + 89 语义） |
| 6 | `outputs/first-run-memo.md` | unit 口径 434 与 sheet 529 行 | 口径合法并存 | 529 是 sheet 行数，434 是**有可提取答案**的 unit 数；两者都要标签 |
| 7 | `outputs/gsm8k-multisample-14b.json` / `.json`（0.5B） | `seeds.per_task` 每题只有 `[9000]` | **真 bug** | 9000–9007（0.5B 为 9100–9107）；已修 runner 并由 jsonl 离线重算 |

分类：**真错 2 处**（#1、#5），**真 bug 1 处**（#7），**口径合法并存 4 处**（#2–#4、#6）。
另外核对时发现 #6 底下还藏着一处旧口径（146/288 与严格重算 128/306），一并记录在 #6；
重跑 audit 又暴露一处**硬件依赖**（#8），不是算错，但文档必须写明。

---

## 1. `multisample-run.md` 的通过分布（真错）

- 原文：§0 与 §1 表写 "30 题中 14 题 0/8、**11 题 1–5/8**、5 题 8/8"。
- 依据：逐行复算 `outputs/gsm8k-multisample-14b.jsonl`（240 行，按 task_id 聚合 pass 数）。
- 实测分布：`{0:14, 1:3, 2:2, 3:2, 4:1, 5:1, 7:2, 8:5}`。
  即 1–5/8 只有 **9 题**，另有 **2 题 7/8**（`gsm8k-test-0215`、`gsm8k-test-0344`），没有 6/8。
- 判定：14+11+5=30 的总数没错，错在把"11 题部分通过"整段写成 1–5/8，漏掉了 7/8 的两题。
- 真值：**14 题 0/8、9 题 1–5/8、2 题 7/8、5 题 8/8**。
- 被改：`outputs/multisample-run.md` §0 与 §1 表格第 4 行。

## 2. directional 425 / 575 / 771（口径：轮次）

- 425 = **round 3** 的 directional 行（n=425，pos 0 / neg 425）。当时没有任何正例，TPR 记为 `–`。
- 575 = **round 5** 新增 150 条 DIR 探针后（n=575，pos 75 / neg 500，TPR 1.00 / TNR 1.00）。
- 771 = **round 10** 再增 98 条（n=771，pos 173 / neg 598，TPR 1.00 / TNR 1.00）。
- 依据：`outputs/results.json` → `summary.pooled_categories.directional = {n:771, n_pos:173, n_neg:598, tpr:1.0, tnr:1.0}`；
  425 与 575 见 memo §3（round-3 表）与 Round-5 addendum 原文。
- 判定：**三个都是真值，是不同轮次的同一个量**，不是矛盾。
- 处理：所有出现处加轮次标签；在 memo 顶部加"当前值（round 10）"框。

## 3. 中位 VCI 0.934 与 0.969（口径：轮次）

- 0.934 = round 3 / round 5 / round 7 的同一值（round 7 记为 0.9342，四舍五入即 0.934）。
- 0.969 = round 10 重跑值。依据：`outputs/results.json` → `summary.vci_median = 0.968526…`（CI 0.904–1.000），
  aligned = 0.985605…（0.986）。
- 判定：真值随轮次变化，**不是冲突**。
- 处理：round-3 主表保留但标 "(historical)"；round-5 的 "unchanged (0.934)" 补注"round-10 为 0.969"。

## 4. 族数 16/20 与 17/20（口径：轮次）

- 16/20 = round 3 的 `families ≥ 0.70`。
- 17/20 = round 5 起（`regex_construct` 因加入 50 条正确 directional 结果由 0.690 → 0.797 跨线；
  泄漏本身没变，见 memo Round-5 addendum）。
- 依据：`outputs/results.json` → `summary.families_ge_0.7 = 17`。
- 判定：合法并存。处理：所有出现处加轮次标签。

## 5. round-10 任务计数（真错）

- 原文："10/100 tasks accepted by the verifier, **89 real failures**（1 parse failure, 88 semantic/format）"。
  10 + 89 = 99，与 100 条任务矛盾。
- 依据：`outputs/realfail-real.json` 100 条记录，`passed = 10`、`failed = 90`；
  `parse_status` = `{ok: 99, no_json: 1}`。
- 判定：失败数应为 **90**，其中 1 条解析失败、89 条语义/格式失败（原文把解析失败从失败总数里漏掉了）。
- 真值：**10 接受 + 90 未接受 = 100**。
- 被改：`outputs/first-run-memo.md` Round 10 §1。

## 6. unit 口径 434 与 sheet 529 行（口径：分母），及 146/288（口径：oracle）

- `outputs/realfail-real-sheet.jsonl` = **529 行**（每行一个 unit），与 `realfail-real.json` 的 `sum(n_units)` 一致；
  20 个族的 `task.items` 合计也是 529。
- 用仓库自己的抽取器（`family.extract_answers`）复算：**95 个 unit 没有可提取的模型答案**，
  因此"有答案可评"的 unit = 529 − 95 = **434**。这就是 434 的来历——它是**分母**，不是另一份数据。
- 旧文 "131/146 gold-correct accepted、0/288 wrong accepted" 与 434 自洽（146+288=434），
  但用严格 gold 复算同一份 artifact 得到 **128/306**（3 个负例被接受，全部是 `base_convert`）。
  差异来源可解释：
  - code_patch regrade 把 15 个 unit 从 wrong 移到 gold-correct（memo §6，counterfactual replay）；
  - `base_convert` 的 `expected` 存的是输入的十进制值，模型答的是目标进制表示（如 expected 1690、答 `3232`），
    严格数值比较把 3 个**验证器判对**的答案记成"负例被接受"。按 round-10 的 regrade oracle 这 3 个算正例，
    于是 128+15+3 = 146、306−15−3 = 288、被接受负例 = 0。
- 判定：**434 vs 529 是分母口径，146/288 vs 128/306 是 oracle 口径**，两个都真，但必须带标签。
- 处理：memo 同时给出 round-10 regrade 口径（146/288）与严格 gold 复核口径（128/306），
  并注明 3 个差异全部来自 `base_convert` 表示法；不改测量逻辑。

## 7. GSM8K summary 的 `seeds.per_task`（真 bug）

- 现象：`outputs/gsm8k-multisample-14b.json` 的 `seeds.per_task` 每题只有 `[9000]`，
  而 `outputs/gsm8k-multisample-14b.jsonl` 实际逐题跑了 9000–9007（240 行）。
- 根因：`examples/gsm8k_multisample.py` 把整题聚合成**一个** task 条目（`seed` 取该题第一个 seed，
  `runs` 只放状态字符串），`vci.passk.compute` 因此只看到每题一个 seed。
  测量结果（n/c、曲线）不受影响，错的只是可审计元数据。
- 修复：runner 改为每个 `(task_id, seed)` 输出一个条目（`runs` 带显式 `run` 索引与状态）；
  两个 summary 用现有 jsonl **离线重算**（未重跑模型）。
- 复核：重算前后 `curves` 与 `status_counts` **逐项相同**（14B pass@1 0.317、pass^8 0.167；
  0.5B pass@1 0.143、pass≥5 全 0）；`seeds.per_task` 现在为 9000–9007 / 9100–9107。
- 被改：`examples/gsm8k_multisample.py`、两个 summary json。

## 8. audit 重跑：aligned 中位 0.986 → 0.978（硬件依赖，不是算错）

- 命令：`python3 -m vci audit --families all --out outputs`（2026-11-05，seed 0，同一台机器）。
- 结果：**pooled 中位 VCI 0.969 不变**、17/20 不变、20/20 reliable 不变、directional
  771（173/598）不变、n_candidates 6854 / n_probes 1628 / scored 1627 全部不变。
- 唯一变动：**aligned 中位 0.986 → 0.978**，mean 0.8064 → 0.8057；追到 `code_patch`
  单族 VCI 0.778 → 0.765、`cheapness` 0.968 → 0.905。原因是 `cheapness` 由实测 p95 latency
  决定（本次机器更吵，p95 0.077 ms → 0.171 ms）。
- 判定：这是**硬件依赖的合法波动**，但也说明 `results.json` 的 manifest note
  "Only latency (cost_ms) is hardware dependent; every other number is a pure function…"
  表述不准确——aligned VCI 通过 `cheapness` 间接依赖 latency。代码未改，只在 memo 与本文标注。
- 被改：`outputs/results.json` / `coverage.csv` / `coverage.md` / `dashboard.html`
  已按本次重跑刷新；memo 中 0.986 全部补注 "round-10 machine; 2026-11-05 rerun = 0.978"。

---

## 发布前检查清单（发布提交 `chore: prepare for public release` 后的状态）

远端状态：发布时配置 `origin = https://github.com/aidless/vci-audit.git`。

1. **LICENSE**：已补根目录 `LICENSE`（MIT，`Copyright (c) 2026 Liu Zewen (aidless)`）；
   `outputs/gsm8k-test.jsonl` 的 GSM8K 来源与 MIT 归属在 README 说明。
2. **仓库名/URL**：`pyproject.toml` 已加 `[project.urls] Repository = "https://github.com/aidless/vci-audit"`；
   README 两处克隆示例的 `<repo-url>` 已替换为真实地址。
3. **版本号**：已统一到 `0.3.0` —— `vci/__init__.py` 与 `pyproject.toml` 升到 0.3.0，向
   `vci/audit.py:625` 的 `manifest.vci_version` 对齐。向上统一而不是把 audit 改成 0.1.0，
   是因为已发布的 `outputs/results.json` 记录的就是 0.3.0，改 audit 侧会让既有产物的版本标签失效。
4. **.gitignore 与大文件**：最大 tracked 文件是 `outputs/gsm8k-test.jsonl`（749 KB），
   全部 < 1 MB，无需 LFS；`work/` 已忽略（LOGBOOK 与 round-12/14 脚本不入库），
   干净 clone 中 `test_side_effect_scan.py` 已自行 skip。
5. **本机路径**：代码目录无本机绝对路径命中（`/home/<user>` 形式）；`outputs` 内的真实轨迹记录含
   `http://localhost:11434` 与模型 digest（这是可复现性证据，建议保留，但在 README 说明"本地模型、非云 API"）。
6. 可选：给 `outputs/` 增加 `README` 索引（哪些是原始数据、哪些是报告）——发布前非阻塞项。

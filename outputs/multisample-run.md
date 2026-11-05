# 多采样 pass^k 实测：GSM8K × 本地 14B（纯 CPU）

目标：让 harness 分解器与 pass^k 计算器第一次跑在真实的多采样数据上，回答
"单次采样报分数是否系统性高估可靠性"，并给出具体倍数。

## 0. 结论

- **14B（主结果，30 题 × 8 次 = 240 次）**：pass@1 = **0.317** [0.179–0.458]，
  pass^8 = **0.167** [0.033–0.300] → **1.90×**（绝对差 15.0 pp）。
- 分布：30 题中 **14 题 0/8**、**11 题 1–5/8**、**5 题 8/8**。pass^1→pass^8
  单调下降（0.317→0.245→0.218→0.203→0.192→0.183→0.175→0.167），
  **在 k=8 时尚未饱和**（k=7→8 仍降 0.008）。
- 判断：**主张成立，但倍数有边界**——1.9×，不是数量级。更难的分布（0.5B 对照）
  能到 2 个数量级，但那种分布下 pass^k≈0，只能支撑"可靠性≈0"的弱陈述。
- 0.5B 对照（难度校准子集）：pass@1 0.143 → pass^2 0.026 → pass^4 0.001 →
  k≥5 全 0，**在 k=4 已饱和**。

## 1. 选型核对（4 条，缺一不可）

| 条件 | 证据 | 结论 |
|---|---|---|
| 1. 公开可下载、许可证允许本地评测 | GSM8K test split，MIT（Cobbe et al. 2021）；官方 raw 地址直接下载，无账号/API key；本地副本 `outputs/gsm8k-test.jsonl` 749,738 B、1319 行、sha256 `3730d312…c39d14` | 通过 |
| 2. 程序化判分 | 仅做数值精确匹配（`vci/gsm8k.py:is_correct`，取 `####` 后末位数，`42.0 == 42`）；无人工、无 LLM 裁判 | 通过 |
| 3. 题短、输出短、CPU 可跑 | prompt 平均 97.9 tokens；`num_predict=16`，实际输出均值 3.31 tokens；单次中位 1.33 s | 通过 |
| 4. 难度足以拉开 pass@1 与 pass^k | 预跑（5 题×8）：acc 0.30，3/5 题部分通过；正式 30 题：14 题全错、11 题部分、5 题全对 → 曲线有真斜率 | 通过 |

反例记录：GSM8K 对 0.5B 模型**过难**（未校准 600 题×2：pass@1 0.041、pass^2 0.002，
近乎全错），曲线会退化为"0"。因此 0.5B 只作为"难度校准后"的次要数据单列（见 §5），
不作为主结果。

## 2. 先算账（全部实测，非估算）

### 2.1 14B Q4 实测速度

- 长生成（5 prompt × `num_predict=160`）：均值输出 139.6 tokens，**中位 1.60 tok/s**。
- 短答（本实验协议，输出 2–3 tokens）：稳态 **1.09 s / 1.24 s**；
  14B 全量 240 次运行中位 **1.33 s/次**、均值 **2.11 s/次**（p90 5.23 s，max 9.28 s）。
- **冷启动陷阱**：模型加载后的第一次调用 **111.5–195.5 s**（加载 + 并发挤压）。
  若只看前两次会误判"每调用要 2–3 分钟"；正确做法是把加载成本单列。

### 2.2 三个候选方案耗时对照

按实测 median 1.33 s / mean 2.11 s 计（不含约 2 min 一次性加载）：

| 方案 | 调用数 | 估算（median） | 估算（mean） | 实测 |
|---|---|---|---|---|
| 20 题 × 8 次 | 160 | 213 s（3.6 min） | 338 s（5.6 min） | 未跑 |
| 50 题 × 4 次 | 200 | 266 s（4.4 min） | 422 s（7.0 min） | 未跑 |
| 100 题 × 2 次 | 200 | 266 s（4.4 min） | 422 s（7.0 min） | 未跑 |
| **30 题 × 8 次（选定）** | **240** | **319 s（5.3 min）** | **506 s（8.4 min）** | **506 s，8.4 min** |

选择理由：三个方案的机器成本同量级（4–8 分钟），而只有 k=8 能满足题目要求的上限；
100×2 只能给 k≤2 的曲线，pass^k 会停在最有信息量的位置之前。故选 30×8。
代价估算误差：naive 319 s vs 实测 506 s（1.59×），差异来自并发负载尖峰。

## 3. 协议（逐题逐次可复算）

- 题目：GSM8K test 官方 1319 行，确定性 stride 选择 `stride = 1319 // 30 = 43`，
  取 index 0, 43, …, 1247；`task_id = gsm8k-test-<index>`。
- Prompt：`Answer only with the final number.\nProblem: {question}\nAnswer:`
  （answer-only，非 CoT）。
- 采样：temperature 1.1、top_p 0.95、`num_predict=16`、`stop=["\n"]`、
  seed = 9000 + j（j=0..7），8 条轨迹/题。
- 判分：末位数与 gold 数值相等（`vci/gsm8k.py`），通过标记随 raw response 同存。
- 记录：`outputs/gsm8k-multisample-14b.jsonl`，240 行，每行含
  task_id/index/seed/attempt/question/gold/raw/pred/status/wall_s/eval_count/
  prompt_eval_count/model。指纹 sha256 `2adee1f4…aa57`。
- 计算：`passk.compute(doc, k_max=8, n_boot=2000, seed=0, alpha=0.05)`，
  任务级 bootstrap CI；`as_failure` 与 `exclude_nonattest` 两种口径结果一致
  （无 timeout/refusal/error，全部为 attest）。
- 复跑：
  ```bash
  python3 examples/gsm8k_multisample.py --n-tasks 30 --samples 8 \
      --model qwen2.5-coder:14b --seed-base 9000 \
      --out outputs/gsm8k-multisample-14b.jsonl \
      --summary outputs/gsm8k-multisample-14b.json
  ```

## 4. 主结果：14B，30 题 × 8 次

| m | pass@m [95% CI] | pass^m [95% CI] | pass@1 / pass^m | 采样成本（s/题） |
|---|---|---|---|---|
| 1 | 0.317 [0.179–0.458] | 0.317 [0.179–0.458] | 1.00× | 2.1 |
| 2 | 0.388 [0.239–0.542] | 0.245 [0.112–0.385] | 1.29× | 4.2 |
| 3 | 0.432 [0.274–0.593] | 0.218 [0.088–0.352] | 1.45× | 6.3 |
| 4 | 0.464 [0.302–0.629] | 0.203 [0.071–0.337] | 1.56× | 8.4 |
| 5 | 0.487 [0.321–0.657] | 0.192 [0.067–0.327] | 1.65× | 10.6 |
| 6 | 0.506 [0.332–0.677] | 0.183 [0.058–0.317] | 1.73× | 12.7 |
| 7 | 0.521 [0.350–0.692] | 0.175 [0.046–0.308] | 1.81× | 14.8 |
| 8 | 0.533 [0.367–0.700] | 0.167 [0.033–0.300] | **1.90×** | 16.9 |

- 成本-成功率：从 1 次采样到 8 次采样，成本 ×8（2.1→16.9 s/题），
  "至少一次成功"只从 31.7% 升到 53.3%（+21.6 pp），"8 次全成功"为 16.7%。
- 尾部：pass^8 由 5 个 8/8 任务贡献（5/30 = 0.167 的精确值），
  所以 CI 下限 0.033 对任务样本量敏感——这是 30 题设计的真实精度，不做平滑。

## 5. 次要数据：0.5B（难度校准子集，明示选择偏差）

- pilot：600 题 × 2 次（1200 次，336 s，median 0.2 s/次），pass@1 0.041 [0.030–0.052]。
- 校准：取 pilot 中至少通过 1 次的 48 题（**在测试集上按难度筛选**），
  重新用 seeds 9100–9107 跑 8 次 = 384 次（47 s）。
- 结果：pass@1 0.143 → pass^2 0.026 → pass^3 0.006 → pass^4 0.001 → k≥5 全 0。
  **在 k=4 已饱和**；pass@1/pass^2 = 5.5×，pass@1/pass^4 = 143×。
- 文件：`outputs/gsm8k-pilot.jsonl`、`outputs/gsm8k-multisample.jsonl`（48×8）。
- 非主张：这批题的 pass@1 绝对值不是 GSM8K 分数，也不可与文献比较。

## 6. 判断：差距是否足以支撑"单次采样系统性高估可靠性"

- 14B：**1.90×**（31.7% vs 16.7%）。方向明确：单次采样报出的是"能解"的比例，
  不是"稳定解"的比例；8/8 可靠性的点估计差 15 pp，CI 边缘相接，
  所以是"系统性但非数量级"的高估。
- 0.5B 难分布：**5.5×@k=2、143×@k=4**，之后 pass^k = 0。倍数更大是因为
  题目对该模型过难，此时只能支撑"稳定性≈0"的弱陈述，不能拿来当一般倍数。
- 可外推的说法：**倍数随难度分布变化（1.9× 到 2 个数量级）**；
  不可外推的说法：**"任何模型都会高估 10×"**。

## 7. 明确的非主张

1. 这不是 GSM8K 官方分数：answer-only、无 CoT、temperature 1.1、
   13B 级量化模型在 CPU 上跑，绝对数字不可与论文表比较。
2. 样本量：主结果 30 题，CI 宽度约 ±14 pp；pass^8 尾部只由 5 题支撑。
3. k=8 尚未饱和，但已接近尾部（pass^9 需要 ≥9 次采样，本次未跑到）。
4. 单机、单模型族（Qwen2.5），未验证其他模型上倍数是否相同。
5. 0.5B 子集经过测试集难度筛选（选择偏差已标注），只能读"估计器差距"，
   不能读"该模型能力"。
6. 本轮没有测 harness 分解器在这批数据上的分工——这两条组件在本轮只验证了
   pass^k 一侧；分解器仍用原有 realfail 数据（见 README）。

## 8. 复现清单

```bash
# 数据集（无账号，MIT）
python3 examples/gsm8k_multisample.py --help   # 首次运行会自动下载到 outputs/gsm8k-test.jsonl

# 主结果
python3 examples/gsm8k_multisample.py --n-tasks 30 --samples 8 \
    --model qwen2.5-coder:14b --seed-base 9000 \
    --out outputs/gsm8k-multisample-14b.jsonl --summary outputs/gsm8k-multisample-14b.json

# 0.5B 对照（先 pilot 再校准）
python3 examples/gsm8k_multisample.py --n-tasks 600 --samples 2 \
    --model evalsft-qwen25-05b:latest --out outputs/gsm8k-pilot.jsonl \
    --summary outputs/gsm8k-pilot.json
python3 examples/gsm8k_multisample.py --n-tasks 600 --samples 8 \
    --model evalsft-qwen25-05b:latest --seed-base 9100 \
    --calibrate-from outputs/gsm8k-pilot.jsonl \
    --out outputs/gsm8k-multisample.jsonl --summary outputs/gsm8k-multisample.json
```

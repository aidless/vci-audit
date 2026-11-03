# 参考材料核实表

核实日期：2026-11-03。核实方式是查出版商/会议页面与论文首页，**没有**逐篇下载全文。
凡是没能拿到权威页面的字段（页码、卷期、DOI），一律标「未核实」，不补写。
DOI 只写查到的；查不到就不写。

字段说明：`状态` 为 `已核实`（作者/标题/出处/年份都在权威页面出现过）、
`部分核实`（主体已核实，个别字段缺失）、`未核实`（只凭记忆，不得引用）。
最后一列「仓库动作」指向本仓库里真正用到该文献结论的代码或文档位置。

---

## 一、标注纪律（怎么问、怎么标、一致性怎么算）

### 1. Artstein & Poesio — Inter-Coder Agreement for Computational Linguistics

- **出处**：Computational Linguistics, 34(4), 555–596, 2008. DOI `10.1162/coli.07-034-R2`。
- **链接**：https://dlnext.acm.org/doi/10.1162/coli.07-034-R2 ；开放版 https://aclanthology.org/J08-4004/
- **状态**：已核实。
- **要读哪部分**：第 2–4 节（agreement measures：observed vs expected agreement、κ 与 α 的区别）、第 6 节（如何报告一致性、样本量）。
- **能拿到什么**：κ 只适用于**两个**编码者、名义标度；多编码者或有缺失值时要用 α。以及「一致性系数不是正确性证明」这一条——两个编码者可以稳定地犯同一个错。
- **对应仓库动作**：`vci/metrics.py::cohen_kappa` / `krippendorff_alpha`；`vci/audit.py::_family_kappa` 的 `synthetic` / `human` / `stability` 三分法；`annotations/PROTOCOL.md` 的「为什么保留 undecidable」。

### 2. Krippendorff — α 的原始定义与序数标度

- **出处（技术报告）**：Krippendorff, K., *Computing Krippendorff's Alpha-Reliability*, University of Pennsylvania 技术报告；不同版本标注 2011 与 2013，**年份存在版本差异**。CRAN 包 `krippendorffsalpha` 引用为 2013。
- **出处（原始论文，未核实）**：Krippendorff, K. (1970), "Bivariate Agreement Coefficients for Reliability of Data", *Sociological Methodology* 2. **卷号/页码/DOI 未核实**，不要引用具体页码。
- **链接**：https://cran.r-universe.dev/krippendorffsalpha/doc/manual.html ；https://journal.r-project.org/articles/RJ-2021-046/index.html
- **状态**：技术报告与序数距离**已核实**；1970 原始论文**未核实**。
- **要读哪部分**：α = 1 − D_o/D_e 的定义；level of measurement 表里的 ordinal 行。
- **能拿到什么**：序数标度的距离函数是**平方秩距离** `δ²(x,y) = (x−y)²`（相邻秩等距），**不是** `|x−y|`。缺失值按 unit 内可配对值处理（`m_u` 个值产生 `m_u(m_u−1)` 个有序对）。
- **对应仓库动作**：`vci/metrics.py::krippendorff_alpha(level="ordinal")`；`outputs/coverage.md` 的 α/κ 对照表；memo 的「两者何时分歧」一节。
- **注意**：本仓库的标签只有 {0,1} 两档，ordinal 与 nominal 在此等价；实现仍按一般秩距离写，以便将来扩到三档以上。

### 3. Sim & Wright — The Kappa Statistic in Reliability Studies

- **出处**：Physical Therapy, 85(3), 257–268, 2005. DOI `10.1093/ptj/85.3.257`。
- **链接**：https://academic.oup.com/ptj/article/85/3/257/2805022
- **状态**：已核实。
- **要读哪部分**：κ 的解释区间（Landis & Koch 的 0.41–0.60 / 0.61–0.80 分档）与「样本量要求」一节。
- **能拿到什么**：κ ≥ 0.60 只是「中等偏上」，不是「可靠」的同义词；小样本下 κ 的置信区间极宽，必须带 CI 报告。**不要**把 0.60 当成校准过的阈值而不加说明。
- **对应仓库动作**：`vci/metrics.py::bootstrap_kappa`；`vci/audit.py` 中 `reliability_gate` 的 `kappa: 0.60`（本仓库自定的工程阈值，不是 Sim & Wright 的推荐值）；`cmd_score` 对每个 κ 都打印 CI。

### 4. MAST — 多智能体失败的分类与人工标注/裁决流程

- **出处**：Cemri, M., Pan, M. Z., Yang, S., et al. (2025). *Why Do Multi-Agent LLM Systems Fail?* arXiv:2503.13657；NeurIPS 2025 Datasets & Benchmarks Track。
- **链接**：https://arxiv.org/abs/2503.13657 ；https://proceedings.neurips.cc/paper_files/paper/2025/file/b1041e52d3be19f0a9bc491657488e4a-Paper-Datasets_and_Benchmarks_Track.pdf
- **状态**：标题/编号/会议已核实；**作者全名单未逐一核实**（只写第一作者 + et al.）。**一致性数值在不同版本之间不一致**：NeurIPS 版写 κ = 0.88，arXiv v1 正文写第二轮 5 条 trace「平均 Cohen's κ = 0.92」。引用时必须带版本，不能笼统写「κ 0.9」。
- **要读哪部分**：§3 的 taxonomy 构建流程（Round 1/2/3 的抽样 → 独立标注 → 分歧讨论 → 冻结分类）；附录的标注指引。
- **能拿到什么**：一个可复制的流程：**先冻结分类法，再算一致性**；分歧不是靠投票压平，而是回到书面指引里补规则。以及「分类法本身是迭代产物」。
- **对应仓库动作**：`annotations/PROTOCOL.md` 的边界情形表（相当于本案的标注指引）；`vci/labeler.py` 的三道校准题（相当于冻结指引后的试标）；memo 的「三人裁决尚未做」限制。

### 5. （补充）τ-bench 的 pass^k 被放到「科学效度」组，见下。

---

## 二、科学效度（样本能不能代表真实失败）

### 5. Jia & Harman — mutation testing 综述

- **出处**：Jia, Y., & Harman, M. (2011). An Analysis and Survey of the Development of Mutation Testing. *IEEE Transactions on Software Engineering*, 37(5), 649–678. DOI `10.1109/TSE.2010.62`。
- **链接**：https://xplorestaging.ieee.org/document/5487526/keywords ；作者版 PDF http://www0.cs.ucl.ac.uk/staff/Yue.Jia/resources/papers/Jia2013.pdf
- **状态**：已核实。
- **要读哪部分**：§2（变异算子分类：AOR/ROR/CR/LCR/UOI/SDL…）、§5（等价变异体与「变异体杀灭」的代价）、§6（高阶变异与 coupling effect）。
- **能拿到什么**：算子不是随手编的，每一个对应一类**句法级**改动；以及「coupling effect」假说（简单变异体互相耦合，能模拟更复杂的缺陷）——这条假说后来被 Just et al. 部分否定。
- **对应仓库动作**：`vci/adversarial.py` 里每个 probe 的 `operator` 字段；`materials/READING.md` 本节；memo「变异算子表」。

### 6. Just, Jalali & Ernst — 变异体能不能替代真实缺陷

- **出处**：Just, R., Jalali, D., & Ernst, M. D. (2014). Are Mutants a Valid Substitute for Real Faults in Software Testing? **FSE 2014**（Proceedings of the 22nd ACM SIGSOFT International Symposium on Foundations of Software Engineering），654–665。DOI `10.1145/2635868.2635929`。
- **链接**：https://dl.acm.org/doi/10.1145/2635868.2635929
- **状态**：已核实。
- **与预期不符**：**不是 ISSTA 论文**。很多二手引用写成 ISSTA，实际是 FSE 2014（同一 DOI 的会议名在 ACM 页面上写着 FSE）。
- **要读哪部分**：§3 实验设置（357 个真实缺陷、5 个开源项目、321k 行代码）；§4 结论（变异体检测与真实缺陷检测显著相关，**独立于覆盖率**）；§5 局限性（变异体分布 ≠ 真实缺陷分布；存在「easier to kill」偏差）。
- **能拿到什么**：变异体是**有用的代理**，但**不是真实缺陷的等价样本**；所以用合成变异体算出的 TPR/TNR 是**效度上限的乐观估计**，不能当成部署时的漏检率。
- **对应仓库动作**：memo「效度上限」一节的核心引文；`vci/adversarial.py` 模块头的「本轮合成样本的效度上限」说明。

### 7. equivalent mutant problem

- **出处**：Offutt, A. J., & Craft, W. M. (1994). Using Compiler Optimization Techniques to Detect Equivalent Mutants. *Software Testing, Verification and Reliability*, 4(3)。**页码未核实**。
  Offutt, A. J., & Pan, J. (1997). Automatically Detecting Equivalent Mutants and Infeasible Paths. *Software Testing, Verification and Reliability*, 7(3), 165–192。
- **链接**：https://www.albany.edu/faculty/offutt/index.html ；https://www.semanticscholar.org/paper/Automatically-detecting-equivalent-mutants-and-Offutt-Pan/5f5cc2b42b0287d71af3a248bcf4ddc493b2abee
- **状态**：1997 论文**已核实**（作者/标题/卷期/页码）；1994 论文**部分核实**（页码未核实）；「等价判定不可判定」这一结论在文献中反复出现，但**原始证明出处未核实**，本仓库只写「文献普遍指出」，不指定证明论文。
- **要读哪部分**：1994 的 compiler-optimisation 检测思路；1997 的约束求解思路；以及两篇的「仍然只能部分自动化」结论。
- **能拿到什么**：等价变异体没有通用自动解法，只能**逐个论证**；因此本仓库不把「语义等价」样本当成「已解决的等价变异」，而是单列一类并给出归因依据。
- **对应仓库动作**：`vci/adversarial.py` 的 `semantic_equivalent` 类与 `attribution` 字段；`outputs/attribution.csv`；memo「等价变异未彻底解决」。

### 8. Ribeiro, Wu, Guestrin & Singh — CheckList

- **出处**：ACL 2020（Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics），4902–4912。arXiv:2005.04118；ACL Anthology `2020.acl-main.442`。
- **链接**：https://aclanthology.org/2020.acl-main.442/ ；https://arxiv.org/abs/2005.04118
- **状态**：已核实。
- **要读哪部分**：§3 的 test type 矩阵：**minimum functionality / invariance / directional expectation** 三类，以及每一类期望的通过/失败方向。
- **能拿到什么**：三类测试对应三种**不同的判定视角**：(a) 最小功能——给定输入至少要做对；(b) 不变性——无关扰动不应改变输出；(c) 定向——特定改动必须让输出朝指定方向变。把这三类混在一起统计 TPR 是没有意义的，必须分类报。
- **对应仓库动作**：`vci/adversarial.py::Probe.checklist_category`；`vci/audit.py::_category_table`；`outputs/coverage.md` 的「三大类 TPR/TNR/FAR90」表。
- **注意**：CheckList 原文是 NLP 行为测试；本仓库只是**借用三类划分**，不是复现它的模板系统。

### 9. Krakovna et al. — specification gaming 案例集

- **出处**：Krakovna, V., et al. (2020). *Specification gaming: the flip side of AI ingenuity*. DeepMind 博客（**非同行评审**）；案例列表最初发布于 2018，后续增补。
- **链接**：https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/ ；https://vkrakovna.wordpress.com/category/machine-learning/
- **状态**：博客与案例列表**已核实**；作者全名单与具体案例编号**未核实**（列表页有版本差异）。
- **要读哪部分**：开头的定义（「字面满足目标但不符合设计者意图」）；案例分组（reward hacking / 利用仿真漏洞 / 钻规则空子）。
- **能拿到什么**：「按字面规格正确、按意图错误」是**一类独立的失败**，不能用「能不能跑通」来判定。本仓库的 `hardcoded_expected` / `overfit_to_tests` 就是这种失败的软件工程版本。
- **对应仓库动作**：`vci/adversarial.py` 的 `hardcoded_expected`、`overfit_to_tests`，以及 memo 里「验证器接受的是字面解，不是意图解」的结论。

### 10. τ-bench 与 pass^k

- **出处**：Yao, S., Shinn, N., Razavi, P., & Narasimhan, K. (2024). *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains*. arXiv:2406.12045；ICLR 2025。
- **链接**：https://arxiv.org/abs/2406.12045 ；https://proceedings.iclr.cc/paper_files/paper/2025/file/1b126cc38b8638e07bef37e7b2bb72bf-Paper-Conference.pdf
- **状态**：已核实。
- **要读哪部分**：§2 的 pass^k 定义：**同一条任务做 k 次独立试验、k 次全部成功的概率，再对任务取平均**；以及给定 n 次试验中 c 次成功时的无偏估计。
- **能拿到什么**：单次通过率会高估「可靠」；要报**重复运行的稳定性**。这正是本仓库把「第二次调用才失败」「非确定性输出」单独列成一类样本的理由：一次性验证看不出它们。
- **对应仓库动作**：`vci/adversarial.py` 的 `stateful_second_call` / `nondeterministic_output` / `cross_task_memory`（operator `STATE`/`NONDET`）；memo 里「单次验证 = pass^1，不是 pass^k」的说明。

---

## 三、引用纪律

1. 上面每条都写了状态；**未核实**的字段（Krippendorff 1970 页码、Offutt & Craft 1994 页码、MAST 作者全名单）不得在正文里当成事实引用。
2. 二手引用（博客、综述转述）不能替代原文；本仓库只在原文/出版商页面上没拿到时，才写「未核实」并说明缺的是哪个字段。
3. 同一文献的不同版本可能给出一致性数值不同（MAST 的 κ 0.88 vs 0.92），引用时必须写「哪个版本」。
4. 本仓库不生成 DOI；表中 DOI 全部来自出版商页面。

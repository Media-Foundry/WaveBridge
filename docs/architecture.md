# 架构

## 目标与成熟度

研究目标是：从显式使用 shuffle、ballot 和 lane/group 索引的既有 ML kernel 中恢复跨线程计算关系，检查改变协作宽度后的计算对象、运算和输出归属，并据此筛选适配候选。

当前交付包括整数点积参考路径、真实 Clang/HIP AST 接入与受限源码结构恢复、独立条件关系检查，以及首例手工 GPU 基线。完整源码关系恢复、通用关系 IR、生产 checker、编译后端和性能策略均未完成。新颖性是待验证假设。

架构采用单仓库、分层库和命令行工具。Python 承担研究编排、协议、参考模型与受限 AST 分析；Clang 提供真实源码 AST。是否引入 MLIR、Triton Layouts 或 Polygeist 扩展点，需经过共同案例实验再作决定。

## 系统分层

| 层 | 目录 | 输入 → 输出 | 职责和约束 | 当前状态 |
| --- | --- | --- | --- | --- |
| 源码接入 | `compiler/frontend/`、`src/wavebridge/frontend/` | 源文件、编译命令 → 原始语义工件 | 保留源码位置、宏展开、编译输入与视图；不猜测数值容限 | JSON fixture、真实 Clang AST、依赖/工具链记录与编译器匹配的原生 capture/cleanup 观测 |
| 关系表示 | `compiler/ir/`、`src/wavebridge/ir/` | 原始语义 → 显式关系模型 | 数据索引、运算、路由、参与条件、存储阶段、输出归属、假设、来源 | 仅版本化 qdot 专用模型 |
| 关系恢复 | `compiler/analysis/`、`src/wavebridge/analysis/` | 原始语义 → 关系模型或拒绝原因 | 支持范围内联合推断；冲突和不确定性必须保留 | 精确调用、列递推、归约、输出后缀、launch 实参及构造字段的受限恢复；调用闭包完整性与整核语义未建立 |
| 关系检查 | `compiler/verification/`、`src/wavebridge/verification/`、顶层 `*_check.py` | 源/目标、输入域、数值协议 → 检查报告 | 独立于生成器；比较输出计算，保留重复计数和保证范围 | qdot 模型及真实 AST 的条件整数、索引、存储、对象初始化/复制检查；仍不证明整核或跨波宽等价 |
| 候选生成 | `compiler/transforms/`、`src/wavebridge/transforms/` | 关系与目标能力 → kernel/launch 候选对 | 数据格式不可随协作宽度修改；候选尚不可信 | qdot 模型 32/64 重新分工 |
| 决策编排 | `src/wavebridge/pipeline.py` | 候选与检查证据 → 接受、拒绝或验证过的 fallback | 未知不接受；所有调用者遵循同一门槛 | 只接受模型候选，不部署 |
| 执行与测量 | `runtime/`、`experiments/` | 已检查代码、设备协议 → 原始执行记录 | 能力探测、正确性测试、计时与环境隔离 | 最小设备探测器；通用执行器待实现 |
| 研究评估 | `benchmarks/`、`research/` | 原始证据、预先声明的协议 → 主张评估 | 覆盖/拒绝/有效接受/错误放行、强基线、成本和性能分开报告 | 登记模板与阶段门槛 |

`compiler/` 保存边界说明和 `frontend/native/capture_plugin.cpp` 原生插件实现；Python采集入口为 `frontend/clang_ast.py` 与 `frontend/native_captures.py`。插件必须匹配Clang版本，观测属于可信前端证据，不是独立证明。`runtime/probes/` 已有可调用的最小 HIP 探测器。尚无通用编译后端或完整适配执行器。探针编译失败、未建立元数据或运行证据不一致，都不能作为目标能力通过的依据。

## 工件流与信任边界

一次完整适配计划包含以下顺序：

1. 固定原始源码、编译命令、launch、合法输入域和外部数值契约。
2. 确认源程序在源语义下有效，记录未建立的前提。
3. 恢复协作关系，并保留每个关系的来源、适用条件及不确定性。
4. 生成完整的 kernel/launch 候选；手工、规则、搜索或 agent 都走相同接口。
5. 独立检查源/目标之间的关系；绑定源、目标、协议和 checker 版本。
6. 为目标设备编译、核实实际波宽，再执行数值和运行时检查。
7. 只对满足对应正确性协议的候选测量性能，与正确兼容基线比较。
8. 决策选取有效候选；否则使用已在同一目标协议下验证的 fallback，或拒绝。

当前参考路径覆盖第 3 步的人工结构化输入、第 4 步的特定模型构造和第 5 步的有限模型关系检查。它没有建立源码与模型的对应。独立的 WB-01 探针和 WB-02 手工基线已覆盖第 6 步的局部设备/数值证据，但没有打通自动适配路径，也没有第 7～8 步的性能比较或部署决策能力。

真实源码路径与qdot参考路径分开：`source.py` 编排受限恢复，各组合checker从绑定的AST重新检查局部义务，而非将分析报告的成功状态直接当作证明。`object_use_closure`的主状态只描述显式引用闭合；`source_order`、`source_reference_use_effects`和`copy_cleanup_observations`分别描述结构顺序、复制效果与复制祖先wrapper的native清理标志，可能各自unknown。最后一项不枚举所有动态析构事件。后续历史值保持必须显式消费所需子报告并解除生命周期、动态非重叠等剩余义务，不能只检查父级status。所有这些路径仍保留整核与部署标记为false。

恢复器、lowering 和模型解释器属于各自保证的可信基础。目标代码与被检查模型之间还需要 translation validation 或明确的可信 lowering 假设；检查了模型不自动证明发出的机器代码。

`verification.launch_binding`提供真实kernel/launch成对工件的静态选点边界：
从同一完整AST fresh绑定kernel定义、callee类型链、形参位置和四个配置表达式。
选择协议绑定root哈希及精确ID，不输入成功结论；输出槽位原始AST和哈希。
它不推断槽位的API语义或字段值，不解除对象保持和设备执行义务，不能单独
作为候选放行门控。此入口与qdot模型pipeline仍分开。
精确选点的状态与全TU launch发现状态分开：其他不同非空ID的未解析位置完整
保留，不默认污染已选位置的绑定；同ID冲突与无法区分身份的情况仍拒绝。

`device_evidence.collect`将该配对、行/线程/列整数关系与共享索引/容量检查放在
同一次调用中；共享支路只接收本次fresh生成的thread报告，根/ABI/选点哈希
核对一致。结果是带完整条件和未解除义务的证据包，不是源程序、目标改写或
部署安全证明；归约值、同步/参与和浮点输出尚未接成统一验证结论。
`collect_rmsnorm`进一步绑定同次归约链、helper、shared索引/容量与fresh输出
结构，再独立检查条件贡献计数；其输出仍为结构证据包，不消除上述语义缺口。

对象复制与捕获各有独立结构入口（`record_copy_check.inspect_effects`、
`capture_source_check.inspect_structure`），不通过假设源存活的值检查去证明源存活。
捕获结构与旧条件身份接口共享路径解析，动态身份仍由旧接口在明确协议下给出。
`object_use_closure.inspect_structure`复用相同引用清单，组合这些独立复制/捕获
结构，不读取alive协议；旧`check`仍提供原条件组合。初始化子报告继续是以正常
返回为条件的报告，不是动态完成证明。历史保持与生命周期门控仍待独立建立，
不能把接口拆分记成这些义务已经解除。

原生前端另提供非穷尽的局部record声明/直接compound作用域/析构声明绑定。
它记录自动存储期与类型的非平凡析构属性，不枚举动态析构事件；for/if初始化
等非直接compound声明保留unsupported。独立对象闭合入口的
`local_record_cleanup_scopes`消费该观测，只分类已观测声明的词法作用域与复制
位置关系，不解除复制前清理、生命周期或历史值保持义务。旧工件缺字段时
该子项unknown，不能推断无析构；清单完整性也未建立。

`preceding_expression_cleanups`补充检查每个copy的词法前缀wrapper，复用相同
native标志绑定逻辑。源初始化和copy祖先的排除项有显式记录，需消费其各自
独立报告；不能因前缀子项checked覆盖祖先unknown。词法较早的lambda body
不等于实际执行，非CompoundStmt分叉不猜先后，所有动态效果义务仍保留。

## 依赖规则

- `ir` 只使用标准库，不能依赖候选生成、硬件或 CLI。
- `frontend` 同时包含严格模型解析与真实编译器采集；源码路径不要求先转成人工qdot IR。
- `analysis` 分别处理参考模型与真实AST；源码恢复与人工契约输入必须带不同的来源标签。
- `verification`及顶层组合checker可调用受限分析器和其他独立checker以fresh重建证据，不能导入 `transforms`、`pipeline` 或候选搜索组件。不能由候选生成器提供自己的通过报告。
- `transforms` 依赖 `ir`；不得改变检查状态，也不得修改 checker 的支持范围。
- `pipeline` 组合生成器和检查器；CLI 只负责命令、序列化与退出码。
- runtime 不参与签发静态关系结论；benchmark harness 不参与核心分析算法。

当前不增加插件注册中心、远程服务、任务队列或 agent 框架。新抽象需要至少两个实际使用者或明确的语义需求。

## 关系模型演进

未来通用模型需要表达五组内容：计算对象及输出写入者；数据访问及别名条件；带运算与重复度的值依赖；collective 路由、成员掩码和收敛条件；跨阶段临时存储及同步。

每条关系都应有源码位置或推导依据，不能用一个置信度分数代替前提。多个解释无法消解时输出 `unknown`。数据格式、算法常量、逻辑宽度和物理宽度分别建模；同一个字面 `32` 不能天然归为同一语义角色。

通用 IR 的设计要先回答量化 GEMV、带广播的归约和一个真实 ballot 案例是否需要共同表示。当前 `qdot-model/v1` 只服务最小接口验证，不应直接扩展成未经设计的通用编译器 IR。

## 支持范围

参考模型支持固定正整数行列数、32/64 逻辑协作组、块内完整逻辑组、规则列遍历、guarded 同步 shuffle-down 加法和每行单一 writer。输出由 `q × scale × x` 单项式累加组成，采用数学无界整数语义。

上述qdot参考模型不支持浮点重排保证、机器整数溢出、ballot、共享内存、真实掩码/收敛语义、任意别名、矩阵指令、warp specialization、动态 shape 或真实物理 wave。尾行按完整逻辑组退出；读取退出组中的 lane 返回 `unknown`。超出资源上限同样返回 `unknown`。

真实AST条件检查另有整数溢出、共享存储/索引等受限支持，不受上述qdot模型列表概括；准确子集和未解除前提见 [检查器说明](../compiler/verification/README.md)。这些局部支持不能升级为完整共享内存并发语义或浮点等价保证。

## 部署与复现

每次实际运行使用独立 `artifacts/<run-id>/`，源与候选工件不可覆盖。配置模板不包含凭据，私有机器地址放在忽略的 `experiments/local/`。实例结果必须带命令、提交号或工作树内容哈希、协议、工具链、设备 ID、原始采样和失败日志。

主分支约定为 `master`，远端为 `https://github.com/Media-Foundry/WaveBridge.git`。本地 CPU 检查是基础门槛；GPU 检查待执行器和 runner 配置建立后启用。构建机是否安装 `hipcc` 不等于 GPU 测试已经执行。

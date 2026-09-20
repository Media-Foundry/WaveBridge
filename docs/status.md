# 当前状态

更新日期：2026-09-20。

## 最新实现：保留全掩码的 XOR 恢复

四参数 XOR 调用新增受限恢复：只支持 width32、int_bits32、显式 unsigned int
全掩码；按精确声明绑定实参，保留 mask AST/类型/range。部分、动态、转换掩码
返回 unknown，不进入路由 checker。全参与和收敛仍是外部前提，不是源码保证。
真实 CUDA 入口重跑 `artifacts/wb03-cuda-source-mask-01/`，自动发现一个 width32
XOR helper，offsets `[16,8,4,2,1]`，block 候选仍为空；实现/AST/源码哈希核对一致。

新增 `experiments/baselines/polygeist_frontend.py`，只记录 MLIR 发射尝试，不
签发 IR 验证或 GPU 结论。270 项测试通过，包括 unsupported mask 不调用 checker
及 mock 工具状态隔离。Polygeist 编译会话 81182 仍在运行，尚无真实同例转换。
交接见 `.agents/handoffs/cuda-mask-polygeist-runner-20260920.md`。

## 最新推进：实际构建与 CUDA 源码分析

LLVM 第二次获取成功，精确检出 `0b9310c6e4416ee48c07edfef81144e22850dfe7`。
首次 CMake 配置通过，但 Ninja 因 unified build 重复定义链接池失败；保留日志，
改用 CMake 自身链接池后，在新目录 `polygeist-cgo24-frontend-build-02` 开始
实际编译。工具构建尚未完成，不宣称 cgeist 可用或同例转换成功。

Sol 使用现有入口对真实 CUDA 端口运行完整 device AST/source 分析，工件在
`artifacts/wb03-cuda-source-01/`：两条列循环、局部贡献、输出与行前缀结构恢复，
归约候选仍为空。四参数 sync shuffle、CUDA builtin cast、坐标和外部语义
仍未支持或建立。主代理核对源码/AST/实现哈希；它仍是同一案例，不算新谱系。
`make check` 258 项通过。交接见 `.agents/handoffs/polygeist-build-cuda-analysis-20260920.md`。

## 最新推进：固定 Polygeist 前端构建准备

新增 `experiments/baselines/build_polygeist_frontend.sh`：核对 Polygeist/LLVM
精确 SHA、拒绝脏源码或已有/源码内构建目录，限并行度，保存工具与命令日志。
配置只用于 CUDA 输入→MLIR 的前端检查，不启用 GPU runtime/backend，不能据此
评价完整重定向。Sol 依据固定源码核对这条路径并审查脚本；主代理完成保护修正。
`make check` 257 项通过，新增六项只验证脚本安全边界，不实际构建 LLVM。

目标 LLVM 提交对象已从子模块远端取得，但第一次检出因 HTTP 408 / promisor
blob 获取失败退出 128；不能称源码已完整或工具不支持输入。已启动同一子模块的
第二次获取，日志 `artifacts/polygeist-source-fetch-02.log`，尚未启动 CMake 构建。
交接见 `.agents/handoffs/polygeist-build-preparation-20260920.md`。

## 最新验证：CUDA 前端实际接入

固定人工 CUDA 输入在真实 CUDA 头文件下通过 host/device 两侧语法检查并取得
kernel AST（AOCC Clang 17.0.6，sm_70）。保留编译器 CUDA 12.1 部分支持警告，
以及缺 cuRAND、缺 nv/target 和未识别 SDK 布局的四份失败报告。
`cuda-syntax-evidence.json` 记录本地证据索引；没有生成机器码、链接或执行 GPU。
Polygeist 已 checkout 论文固定提交，LLVM 子模块尚未初始化，G1 对照仍未执行。
完整命令和边界见 `.agents/handoffs/cuda-syntax-20260920.md`。
本轮 `make check`：251 项测试通过，六份原始报告的索引哈希全部复核一致。

## 最新提交验收：CUDA 共同输入准备

新增首例 RMSNorm 的人工 HIP→CUDA API 移植及来源哈希清单，保留原协议。
CPU 回归核对三个计算函数体除明确的 shuffle API 替换外与 HIP 父版本一致；
这不是语义等价证明，也不增加生产 kernel 谱系。主代理重跑 `make check`，
250 项测试通过。CUDA 编译、CUDA GPU 执行与 Polygeist 共同案例对照尚未建立，
G1 不因此通过。按用户要求在当前分支直接 commit，不创建 PR、不推送。
交接见 `.agents/handoffs/cuda-common-input-20260920.md`。

## 已落地

- 仓库分层、模块依赖规则、协议和设计决策记录。
- 根 `AGENTS.md` 的中文回复约定，`.agents/` 的职责、流程和交接模板。
- 无外部运行时依赖的 Python 包、CLI、严格 JSON 模型输入。
- qdot 固定形状无界整数参考模型，显式 shuffle-down 阶段和输出多项式检查。
- 模型级 32/64 候选生成，kernel/launch 联动，量化分组保持不变。
- 合法/错误候选示例、CPU 回归测试及 GitHub Actions 工作流定义。
- benchmark 来源/谱系/基线协议，实验配置和证据模板，候选主张及相关工作核实表。
- Git 主分支约定为 `master`，origin 指向 `Media-Foundry/WaveBridge`；初始化前确认远端为空仓库。
- WB-01 最小 HIP 设备探测工具：分阶段报告、命令与原始日志、工件哈希、超时与拒绝状态；工具实现不等于硬件门槛通过。
- WB-02 固定 llama.cpp RMSNorm 的完整上游快照、MIT 许可、手工特化补丁、独立 reference、冻结数值协议和隔离的人工 oracle；W7900 上完成有限输入的 logical32 基线实测。

## 尚未完成

- HIP/CUDA 源码关系恢复与通用关系 IR。
- 通用跨 lane checker、ballot/掩码/共享内存/浮点协议支持。
- Clang/LLVM 集成、目标代码生成及模型到生成代码的一致性检查。
- MI250 接入、实际 wave64 验证、正确兼容 fallback 与通用 GPU runner。
- 多谱系真实 kernel 语料、Polygeist/CKTI 共同案例验证、强人工原生基线复现。
- 性能数据、端到端部署、人工成本数据、创新性结论和论文结果。

## 验证记录

2026-09-20 的本地验收（Python 3.12.7）：

- `make check`：42 项 CPU 测试通过，另包含 40 组行列边界组合的子用例。
- `make demo`：32→64 模型候选获得 `checked`，量化分组保留为 32，grid 从 2 更新到 3。
- `python3 -m pip wheel --no-deps --no-build-isolation .`：wheel 构建成功。
- 在独立临时虚拟环境安装 wheel，离开源码目录并清除 `PYTHONPATH` 后执行 `wavebridge demo`：成功。
- 全仓 JSON/TOML 解析、Markdown 相对链接和尾随空白检查：通过。

以上 G0 本地验证不代表 GPU 正确性或性能；当时没有执行 GPU kernel。后续设备探针见下节，GitHub Actions 的实际状态以对应提交的运行记录为准。

## WB-01 / WB-02 首轮门控

WB-01 由一个 GPT-5.6 Sol 子代理实现，主代理负责验收；保留原有 qdot 路径和整数检查范围。

本机 `rocminfo` 可见两个 gfx1100 GPU agent。探测时的 `rocm-smi` 采样显示两卡空闲、无 KFD PID；这只是设备可见性和负载采样，不证明实际波宽。

两条工具链尝试均未执行 kernel：

- 默认 Conda `hipcc`：链接阶段缺少其配置引用的 `libamdhip64.so`，报告 `compile_failed`。
- `/opt/rocm/bin/hipcc`：缺少 `hip/hip_runtime.h`，报告 `compile_failed`。没有安装工具链或混搭 headers/runtime。

上述失败报告保存在本地 `artifacts/wb01-*/report.json`，每次尝试独立记录。它们的 metadata、execute、semantic validation 均未建立，后续成功记录不覆盖这些失败。

最终验收：主代理重跑 `make check`，55 项测试通过（原 42 项和探测器 13 项）；检查通过 `git diff --check`。最终本机报告为 `artifacts/wb01-20260920T065807Z-618484-d01566/report.json`，HIP 源码与 runner 副本哈希均核对一致。CPU mock 状态测试不替代设备执行证据。

继续推进后的 WB-01 实际执行：

- 确认已安装的同一 `_rocm_sdk_core` wheel 中存在匹配的 HIP 7.15.26333 头文件、clang、device libraries 和 `libamdhip64.so.7`，缺的是 unversioned 开发链接名和默认查找布局。
- `prepare_sdk_view.py` 在项目 `artifacts/toolchains/` 建立显式 linker 视图及编译参数；没有安装新包、修改原 SDK 或混用系统和 Conda 的库。
- `HIP_VISIBLE_DEVICES=0` 下 W7900（gfx1100，PCI `0000:53:00.0`）探针成功执行，设备属性、device `warpSize`、ballot、shuffle 与同次编译的具名 kernel 元数据一致为 **32**。
- 最新报告为 `artifacts/wb01-20260920T074250Z-639474-321f6d/report.json`，状态 `verified`；包含源码、runner、SDK view manifest 和二进制哈希。
- 本次通过仅覆盖这张 W7900 的普通 wave32 探针。没有验证 MI250、native64 候选、模型到机器码等价或性能收益。

WB-02 首例实际执行：

- 案例来自 llama.cpp `b23efaa2ef147f547ee75cbf0c621d61904de80e` 的 `rms_norm_f32<256, false, false>`；保留 logical32 XOR shuffle、共享 partial、barrier、第二次归约与广播。standalone 是有完整补丁记录的手工特化，不是自动恢复结果。
- 首次编译因 `rsqrtf` 声明缺失失败，报告 `artifacts/wb02-20260920T074914Z-9daaf0/report.json` 保留。随后显式接入同 SDK 的 HIP math 声明及 Clang wrapper 使用的 OCML 入口；没有改为 `1/sqrt` 或放宽数值协议。
- 同一 W7900、`HIP_VISIBLE_DEVICES=0`，`3×777` 输入全部 2,331 个输出通过；最大绝对误差 `1.1920928955078125e-7`。报告 `artifacts/wb02-20260920T075245Z-3bc452/report.json`。
- 另测 3 行、列数 `1, 31, 32, 33, 255, 256, 257, 1023` 的 8 个确定性输入，均通过。所有比较使用运行前冻结的 `atol=1e-5`、`rtol=2e-5`，epsilon 为 `1e-5`。
- 报告绑定源文件、协议、reference、输入/输出、二进制和 WB-01 证据，并核对运行时设备身份。探针波宽不等同于对 RMSNorm 最终机器码的独立波宽验证。
- 这只证明所测输入的数值通过，不证明整个合法输入域、原上游所有分支、自动源码关系恢复、native64 正确性或性能收益。G1 的先前工作差异仍未建立。
- WB-02 最终本地 `make check`：71 项 CPU 测试通过；包含来源哈希和证据边界回归。设备原始工件保存在本地 `artifacts/`，Git 中的 `benchmarks/cases/llama-rmsnorm/evidence.json` 仅提供索引与哈希，不是完整公开复现包。

## 下一项研究任务

WB-03 已开始源码接入：`frontend/clang_ast.py` 调用真实 Clang，保留多 JSON 根、
函数位置、命令、工作目录及源码/编译器哈希，并区分失败状态。设备视图需显式
`--cuda-device-only`；默认 HIP 可能同时输出 host/device，不能混为单一语义。
本机新入口成功采集 RMSNorm kernel、warp helper、block helper，各一份设备 AST，
报告位于 `artifacts/wb03-ast-J5vhJF/`。源码 SHA 与 WB-02 实测版本一致。
这不读取人工 oracle，但尚未建立常量/调用闭包、launch 对应或跨 lane 关系。
G1/G2 均未因此通过。后续按用户要求直接 commit，不再创建 PR。
本轮 `make check` 81 项 CPU 测试通过，含多 JSON 根、超时日志、非法超时和
禁止覆盖源码/已有工件的回归；没有执行新的 GPU 数值或性能实验。

WB-03 后续增加 `analysis/source_facts.py`：从真实 AST 提取直接调用、声明
引用、运算符和循环，保留源码范围。三个 HIP 函数的结构事实在
`artifacts/wb03-facts-Fnn8eF/`，可见 `__shfl_xor`、`__syncthreads`、helper
和 OCML 调用。`threadIdx.x` / `blockIdx.x` 的 HIP 属性 getter 仍标未知；
没有把仅有引用的 `kLogicalWidth` 猜成常量 32。输入工件哈希与 root index
隔离 Clang ID，不跨编译猜连边。真实 C++ 改名与嵌套间接调用回归通过；
该测试 fixture 不是 ML benchmark，不计入真实语料覆盖。
本轮最终 `make check` 91 项通过，其中 2 项使用本机真实 Clang；没有 Clang
的环境会显式跳过这 2 项，不能把跳过记为真实编译验证。跨 lane 恢复仍未完成。

WB-03 声明接入继续推进：新增完整 translation-unit 模式及 root-local 声明索引。
真实 HIP 工件 `artifacts/wb03-tu-hgtXLo/rmsnorm-tu-single.json` 与
`rmsnorm-index.json` 已生成，确认同次 AST 中 `kLogicalWidth`、`kBlockSize`
含 initializer，warp helper 含 body；完整 TU 索引仍有 2 个 unresolved 引用。
这不代表所有声明闭包或线程 getter 语义已建立。
两次 1.5 GiB 虚拟内存限额下的序列化失败保留为空/部分 JSON 文件，不能消费为
成功报告；改为流式写出并去除重复 AST stdout 后，同限额运行成功。
最终本地 `make check` 98 项通过（含 3 项真实 Clang 测试）；未运行新 GPU kernel。

WB-03 受限整数常量求值已接入：`integer_constants.evaluate` 从同 root 精确
声明 ID 和初始化表达式计算 signed-int 常量。当前 HIP compiler 的
`__INT_WIDTH__=32` 已通过预定义宏核对，调用时仍显式传入 `int_bits=32`。
在上述完整 HIP AST 上得到 `kLogicalWidth=32`、`kBlockSize=256`，保留
声明与表达式 range；没有按名字填值，也尚未自动判断常量的协作/格式角色。
每步检查有符号溢出，C++ 向零除法和负余数；volatile、unsigned、未支持转换、
缺定义、循环引用及除零返回未知。真实 Clang 回归覆盖常量改名、声明引用
乘法和负数除余；全仓 `make check` 106 项通过（含 4 项真实 Clang 测试）。
本轮未执行新的 GPU kernel，线程 getter 的自动语义解释仍未完成。

WB-03 getter 追踪取得源码证据：`return_trace.trace` 在单 return、无参数
wrapper 子集内沿同 root 精确 ID 追踪。实际完整 HIP AST 中，threadIdx 的
`__get_x` 经 `__hip_get_thread_idx_x` 到 `__ockl_get_local_id`；blockIdx
对应链到 `__ockl_get_group_id`。两条外部调用都保留维度 0 的原始实参 AST
及转换，不自动移除 size_t/unsigned 转换或赋予外部接口语义。
真实 Clang fixture 验证改名、维度0/1变化、多语句/额外算术拒绝；fixture
不计入ML语料。下一步需把调用证据、目标外部接口协议及可达表达式连接起来。
最终本地 `make check` 114 项通过，其中5项使用真实Clang；工作未涉及性能测量。

WB-03 首条源码到列递推路径已运行：`python3 -m wavebridge.source` 直接输入
WB-02 HIP standalone，采集同次完整 AST 后恢复两个列循环的声明起点、参数
边界与步长256，不读取人工 Kernel JSON。工件在
`artifacts/wb03-source-columns-01/{ast,report}.json`，源码 SHA 与基线一致，
报告绑定 AST 字节哈希，`checked=false`、`deployable=false`。
真实Clang改名/步长128变体反映源码变化；额外induction/bound写入、引用别名、
调用与复杂控制流保守未知。全仓 `make check` 123 项通过，其中7项真实Clang。
该递推带无溢出、合法输入域和别名等未证明前提；起点尚未自动解释为线程ID，
数据覆盖、host launch 与collective路由均未检查，不能宣布WB-03或G2完成。

WB-03 源码入口现已连接起点声明的初始化调用证据：两个循环共用的 const
`tid` 初始化表达式含 HIP 属性 getter，精确调用链到 `__ockl_get_local_id`。
报告保留完整 `PseudoObjectExpr`、receiver、转换与实参；不选某个child冒充
初始化结果，值等价和起点语义仍明确未建立。
本轮 `make check` 130 项通过，含8项真实Clang；MS属性改名/额外算术及
特殊调用未知回归覆盖这一边界。源码报告新增分析实现文件哈希，无新GPU执行。
最终完整源码重跑工件在 `artifacts/wb03-source-origins-02/{ast,report}.json`，
两个step仍为256，共用起点的调用证据为OCKL local id，语义标记仍为unknown。

WB-03/04 的首项通信路由证据：真实 HIP `warp_reduce_sum_logical32` helper
恢复出width32与offsets `[16,8,4,2,1]`、同一accumulator的加法与返回关系。
在外部声明的全参与logical-XOR快照语义下，独立checker枚举全部32个lane，
确认每个输出恰好含每个初始贡献一次。持久报告为
`artifacts/wb03-xor-evidence-01.json`，绑定既有完整AST文件哈希。
真实Clang改名/width64源码变体也完成恢复与条件路由检查；这是CPU模型检查，
不是native64 GPU执行。缺阶段/重复阶段被拒绝。`make check` 140项通过
（含9项真实Clang测试）。intrinsic语义、参与收敛、浮点值、共享内存第二阶段、
输出归属和候选源码检查尚未建立，WB-03/04及G2/G3均不能算整体通过。

WB-03/04 继续接入共享 partial：真实 HIP 基线的 block helper 已恢复七阶段
结构，得到 block_threads=256、width=32、writer_lane=0。联合证据保存于
`artifacts/wb03-block-evidence-01.json`，绑定完整 AST 哈希；独立 block checker
在声明的坐标、全参与、XOR 和共享可见性前提下，确认 8 个 partial 汇集的
每个输出包含全部 256 个初始贡献各一次。21 处转换记录保留类型与源码范围，
`conversion_semantics=not_established`，不能推断 unsigned→int 转换可消除。
本地 `make check` 151 项通过；新增真实 Clang unsigned-coordinate 回归，
缺 barrier、错误 shared 下标、遗漏/重复贡献等分别按范围返回 unknown/rejected。
完整源码仍 `source_program_checked=false`，没有新 GPU 运行、浮点等价或自动候选。
工件仅保存在本地，不等于已发布复现包。

WB-03 源码入口已接入按精确直接调用发现归约候选，不再要求手填 helper、
shuffle、barrier 的 AST ID。最终真实 HIP 重跑工件为
`artifacts/wb03-source-reductions-02/{ast,report}.json`：遍历 9 个有定义的函数，
3 次结构尝试，发现一个 block256/width32 共享归约及一个 width32 XOR helper，
offsets 为 `[16,8,4,2,1]`。保留 23 条未解析调用诊断，预算未耗尽但
`analysis_complete=false`；不自动把候选结构检查升级为源码正确性结论。
AST 与全部实现文件哈希复核一致；`make check` 158 项通过。真实 Clang 测试
确认不可达相似 helper 不纳入候选；局部 callable、间接/特殊调用及预算边界
有独立回归。首轮 `wb03-source-reductions-01` 与编辑并发，保留但不作最终证据。

WB-03 调用发现已支持声明明确为 static 的精确成员调用。真实 HIP 重跑工件
`artifacts/wb03-source-static-members-01/{ast,report}.json` 增加四条属性 getter
调用边，可达定义从 9 个变为 13 个，两个归约候选不变；receiver AST 保留，
不赋予线程坐标语义。21 条剩余诊断为 17 条不支持的 callee cast、3 条缺唯一
定义和1条缺成员声明；分析完整性仍为 false。实现哈希核对一致，本地
`make check` 161 项通过，包括真实 Clang static property 和 virtual 拒绝回归。
本轮未执行 GPU kernel，也未解除外部 intrinsic 或数值语义前提。

WB-03 的 17 条 callee 转换现已从真实 AST 确认为 `BuiltinFnToFnPtr`，
调用发现器记录其精确声明边及 callee 转换证据，不赋予 builtin 语义。
重跑 `artifacts/wb03-source-builtins-01/{ast,report}.json` 得到 17 条 builtin
调用边；原有两个归约候选保持不变。未解析总数仍为21，原因现在明确为20条
缺唯一函数体和1条缺成员声明，不将外部实现边界伪装成分析成功。
实现哈希核对一致；`make check` 163项通过，含真实Clang builtin及BitCast拒绝
回归。没有新GPU执行或完整源码保证。

WB-03 已连接局部平方和与消费调用：真实源码入口工件
`artifacts/wb03-source-contribution-01/{ast,report}.json` 恢复零初值累加器、
`input[col]` 的平方累加与步长256递推；consumer 精确声明 ID 与此前自动
发现的块级归约 helper 相同。前置线程索引/指针定位只记录范围，明确
`prefix_scope=not_analyzed`；别名、线程坐标和浮点语义仍未建立。

独立 `verification/column_coverage.py` 按同余序列检查列覆盖/重复度，成本
不随列数线性展开，并检查最后一次 signed 增量溢出。5625个小域组合与枚举、
3584个小位宽组合与逐步溢出模拟一致。条件证据
`conditional-column-coverage.json` 对777/4096/10亿列通过，起点0～255是显式
外部假设，不冒充恢复出的线程坐标，也不是GPU实测尺寸。本轮 `make check`
176项通过；错误下标、非零初值、不同乘数、额外更新、条件消费及副作用实参
均有拒绝回归。实现哈希核对一致，未生成GPU候选或声明整核正确。

WB-03 后缀关系已连接：`normalization_output` 从局部贡献继续恢复
`total = consumer(...)`、`scale = external(total/count + epsilon)` 与
`output[col] = scale * input[col]`。真实 HIP 重跑工件为
`artifacts/wb03-source-output-01/{ast,report}.json`，consumer 与自动发现的
块级 helper 相同；读写循环起点、边界声明和步长256对应。记录14处转换，
包含 IntegralToFloating，转换语义仍未建立；不按外部函数名认定rsqrt。
AST及实现哈希核对一致；`make check`181项通过。错误列/步长/输入、count
不对应、额外写入、嵌套scale调用和尾随语句均有拒绝回归。前缀行基址、launch、
alias、外部接口及浮点关系仍未证明，无新GPU执行或部署候选。

WB-03 已接入严格行偏移前缀：真实 HIP 工件
`artifacts/wb03-source-prefix-launch-01/{ast,report}.json` 中输入/输出指针更新
引用同一row/count，完整offset外层及row/count转换链对应，记录10处转换。
列起点与前缀start声明关联，row/start各保留一条getter调用证据；不把getter
结果自动解释为block/thread坐标，也不从long类型拼写断言整数位宽。
`launch_facts` 同时记录同root精确kernel引用的一个launch，保存4个配置实参
及4个kernel实参AST；dim3值、host可达性和kernel/launch数值一致性未验证。
`make check`190项通过；单侧offset外层窄化、错误row/count/target、间接launch
及不完整配置均有拒绝/未知回归。AST和实现哈希核对一致，无新GPU执行或适配候选。

WB-03 launch 实参已按唯一kernel定义的位置关联4个形参，缺定义/数量不匹配
时保留unknown。`constructor_arguments` 保存精确构造引用及参数位置、默认来源
和转换链，转换前常量不作为实际维度值。真实HIP工件
`artifacts/wb03-source-launch-arguments-01/{ast,report}.json` 的block构造参数为
转换前256/1/1，首项与归约helper的BLOCK引用同一声明；grid首项symbolic，后两项
的默认1来自AST内容。AST和实现hash核对一致。
本机普通Clang将测试构造表示为不带精确constructor ID的CXXTemporaryObjectExpr，
该路径正确返回unknown；不按类型名补猜。`make check`196项通过。字段映射、
转换后值、实际grid/block及运行时launch一致性仍未证明，没有新GPU执行。

WB-03 构造字段已按精确声明恢复：真实HIP工件
`artifacts/wb03-source-constructor-fields-01/{ast,report}.json` 中两个配置构造均
得到x←参数0、y←参数1、z←参数2，并核对直接所属record全部字段。字段交换的
真实Clang fixture恢复成显式交换关系；额外body写入、base/delegating、算术或
不支持转换保持unknown，不从字段名字猜参数位置。
只读ABI探测 `artifacts/wb03-abi-macros-01/report.json` 保存device-only空TU
预定义宏（int32、long/long long64）与原始命令输出，不能替代完整源码ABI绑定。
独立区间转换checker在显式int32→unsigned int32条件下确认256/1/1值保持，
证据在上述源码工件目录 `conditional-conversions.json`，绑定宏/源码报告与
checker哈希；full_source_abi_binding仍未建立。`make check`206项通过，
实现hash核对一致，无新GPU执行或完整适配保证。

WB-04 新增独立构造字段常量检查器及 `wavebridge.configuration_check` 入口，
将实参转换链、精确构造声明和完整字段位置映射连接到外部整数 ABI 表。
报告绑定输入字节及实现哈希；缺失配置、symbolic、未知 ABI 保持unknown，
不值保持的整数转换被拒绝。`source_program_checked=false`、`deployable=false`
始终保留。真实既有源码报告的block条件字段值为256/1/1，grid含symbolic，
整体保持unknown；`make check`217项通过，检查器实现hash核对一致。
具体验收与本地产物见
`.agents/handoffs/wb04-configuration-20260920.md`；并非实际launch或GPU保证。

WB-03 新增 launch 前置整数守卫恢复。真实HIP重跑工件
`artifacts/wb03-source-launch-guards-01/{ast,report}.json` 中，grid首实参的
精确声明对应必要区间 `[1,8]`，列数kernel形参的host实参声明对应 `[1,1023]`。
5个不用于区间推导的普通错误检查保留为skipped；跳转绕过、非只读使用等拒绝。
这些不是合法输入协议、host可达性或GPU保证；配置模型检查仍整体unknown。
`make check`227项通过，源码/AST/实现hash核对一致，无新GPU执行。
完整命令见 `.agents/handoffs/wb03-launch-guards-20260920.md`。

WB-04 构造字段checker新增显式闭区间模式，CLI必须启用
`--use-host-guard-assumptions`，并核对launch ID、报告状态和整数位宽前提。
复用上一轮真实源码报告，`configuration-interval-check-01.json` 在显式前提
下检查grid字段域[1,8]/1/1与block常量256/1/1；未启用选项的
`configuration-default-check-02.json`仍unknown。两个工件均在
`artifacts/wb03-source-launch-guards-01/`。236项测试通过，输入/实现hash一致，
含136个小位宽闭区间枚举对照；没有新增源码编译或GPU执行。
区间/常量明确分开，仍不证明实际launch或GPU等价，部署标记false。
完整交接见 `.agents/handoffs/wb04-configuration-intervals-20260920.md`。

WB-04新增单个kernel标量整数实参域检查。真实报告输出
`artifacts/wb03-source-launch-guards-01/kernel-argument-domains-01.json`中，
列数参数按精确形参ID关联区间[1,1023]，条件转换checked；指针和浮点参数
仍unknown，整体partial。244项测试通过，无新增源码编译或GPU执行。

G1定向核查已锁定Polygeist论文提交 `ba9953a08c9b` 及LLVM子模块，阅读论文
与固定入口源码；CKTI只核实出版元数据，全文/实现未取得。PATH未发现cgeist
不等于工具语义不支持；两个方法均未执行共同案例。详见
`research/baseline-checks-20260920.md`，交接为
`.agents/handoffs/wb04-kernel-arguments-g1-20260920.md`。

以首例明确源码恢复的最小支持子集：XOR shuffle、共享内存归约与广播、规则列遍历；先建立源码位置到关系的对应，不扩通用 IR 或调优平台。Polygeist/CKTI 对同一案例的能力仍待核实；尚不能宣布 G1 通过。MI250 接入、WB-03 完整关系恢复与 WB-04～08 仍待实施。

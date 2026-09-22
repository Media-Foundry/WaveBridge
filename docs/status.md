# 当前状态

更新日期：2026-09-22。

## 原始构造实参与字段域的 fresh 组合

新增 constructor_source_check：在完整 TU 中按唯一直接构造表达式 ID，重新
恢复身份、原始实参及字段映射；literal/default 独立核对来源和转换，动态实参
逐项 fresh 运行 minimum checker，再连接实际形参及字段初始化转换。
外部仅提供声明域，不接受自报 checked；缺失、多余和错绑定的域均不放行。
原始恢复报告保持其真实 unknown 等状态，只有全部字段义务满足才输出组合 checked。

本地 553 项 CPU、86 项真实 Clang 专项和 demo 通过；ROCm Clang 23 下新增
8 项通过。覆盖多个动态实参、字段交换、默认 7/13、错误函数、构造体写入、复制、
窄化、伪造报告及类型/ID 畸形输入。未运行 GPU，实际 launch、copy 和输入域
来源未建立；WB-03 未完整验收。完整证据见
`.agents/handoffs/wb04-source-constructor-20260922.md`。

固定完整 vLLM TU 的真实原始构造，在 hidden_size∈[1,4096]、int/unsigned int32
的显式诊断前提下，字段 x∈[1,1024]、y=z=1 得到条件 checked；八个实现文件
前后哈希一致，原始实参恢复仍为 unknown。没有建立这些字段的实际 launch 语义。

## 动态整数选择的条件值检查

新增 integer_selection 独立检查器：从完整 TU 的唯一表达式及精确 callee ID
核对两个 const 内建整数引用参数、单 return 的 `<`/三元 minimum 关系，不按
函数名推断。只支持普通整型声明或字面量临时实参、立即值读取及值保持转换；
输入域和 ABI 显式给定，未知域、错误选择、副作用、引用逃逸不放行。

本地 545 项 CPU、78 项真实 Clang 专项和 demo 通过；ROCm Clang 23 下新增
8 项也全部通过。独立小域枚举核对两变量区间，包含比较方向交换、long、负数、
窄化及声明/参数 ID、临时对象存储期篡改回归。未运行 GPU，不自动升级构造字段、
实际 launch 或 WB-03 验收。完整重放记录见
`.agents/handoffs/wb04-integer-selection-20260922.md`。

固定完整 vLLM TU 的真实 block 首参，在显式 hidden_size 域 [1,4096] 和
int/unsigned int32 ABI 前提下条件 checked，结果 [1,1024]；三个实现文件
前后哈希一致。该域不是从 Tensor.size 或 launch 自动恢复，不是新 holdout 成功。

## 构造默认实参的声明来源

直接构造路径现可将无子节点的默认实参关联到选定构造参数的本地整数字面量，
保留原始调用点 AST、参数 ID/位置和默认子树，不猜测缺省值。字段 checker
独立复核报告内来源、位置、类型和转换链；同 TU 唯一性及重声明排除仍由前端
建立并列为显式前提。调用/立即函数、来源缺失或歧义保持 unknown，窄化拒绝。

本地 537 项 CPU、70 项真实 Clang 专项及 demo 通过；Clang 23 定向共 11 项，
9 项通过、2 项因编译器直接提供默认子树而跳过来源补全路径测试。非 1 默认值、
报告篡改和括号类型不连续均有回归。未运行 GPU，WB-03 未完整验收。
完整 TU 重放与局限见 `.agents/handoffs/wb03-default-sources-20260922.md`。

## Clang 类型打印差异的 CI 修复

8b0117d 的远端 run35741316610 三任务失败：Clang 18 省略同拼写
desugaredQualType，direct constructor 将它误判为类型不匹配。现仅在键缺失时
回退 qualType，仍要求精确 alias→record ID 和 RecordType 拼写相等；不是按名称
推测类型。新增同拼写省略正例及缺锚点/不同拼写/空值负例。
本地 532 项测试、65 项 Clang 专项和 demo 通过；ROCm Clang 23 下 6 项定向
测试通过。修复提交 c1aaf73 的远端 run35741730545 三任务全部 success，含
Clang 18 专项及 Python 3.11/3.12。未新增 GPU 或 launch 域结果。

## 命名 launch 配置的直接构造身份

constructor_arguments 新增 alias→精确 record ID→唯一选定 ctorType 的直接
CXXConstructExpr 入口，不按 dim3 名称猜测；原 conversionFunc 路径保留。
531 项 CPU 测试、64 项 Clang 专项与 demo 通过，覆盖同名不同 namespace、
标量字段检查、copy 保持 unknown、缺默认来源、未知调用和身份/预算负例。

完整 vLLM TU 重放已精确关联 launch 的 block copy 与声明时三 uint 构造，
三个实现文件前后 hash 一致。copy 字段语义仍 unknown；原构造的 min 调用和
缺默认实参来源仍阻断值检查，没有实际 launch 域通过。另已定位按引用捕获和
hidden_size 的 long→int 转换；后续必须逐项连接，不将声明时值视为 launch 时值。
未运行 GPU，详见 `.agents/handoffs/wb03-direct-constructor-20260922.md`。

## 坐标循环体的条件保持组合

新增 column_body 独立入口：完整 TU 精确定位函数/直接循环，fresh 观察 header
并推导受保护声明；循环体内 1～8 个属性必须逐项重新检查 receiver/getter。
其它节点继续受原副作用和存储目标限制，默认 column_loops 恢复行为不变。
外部源码有效性、无别名及属性协议须精确绑定，缺失或自报 checked 不可放行。

526 项 CPU 测试、59 项真实 Clang 专项及 demo 通过。包括合法数组写入/只读
cast、多属性、修改 induction/边界、隐藏引用、下标 col++、不透明调用、静态
induction、错误上下文与协议错绑定。结论只为 body 保持受保护声明，不是整个
body 无写、header 递推、列覆盖或整核验证；未运行 GPU，WB-03 未完整验收。
固定完整 vLLM TU 的 float 首个循环体在显式诊断前提下条件 checked，扫描
3,705,324 节点，七个实现文件前后哈希一致；未建立实际 launch 域或新 holdout
成功。完整 TU 诊断与工件绑定见 `.agents/handoffs/wb04-column-body-20260922.md`。

## 单属性表达式的 receiver/getter 条件组合

initializer_value 新增独立 receiver observation，不改变旧 link 状态或 purity：
核对同TU唯一extern、非TLS/reference/volatile、无initializer声明及类型一致性。
getter_returns 新入口按完整root中的唯一expression ID fresh恢复receiver和getter，
要求分别绑定的显式协议，不接受外部自报checked。518项CPU测试、54项Clang专项
和demo通过；未放宽column_loops的body门控。

固定完整vLLM TU的一个blockIdx.x原始属性表达式，在显式receiver readiness/
扩展求值、leaf域/ABI/无写/正常返回前提下条件checked；四个实现文件运行前后
hash一致。前提引用仍unverified，不代表整个loop、实际launch域或vLLM整核checked。
未运行GPU，下一步处理循环体组合和实际坐标域。见
`.agents/handoffs/wb04-property-effects-20260922.md`。

## 精确 builtin callee 支持与完整 TU 条件检查

getter_returns 已支持直接调用位置的零参 BuiltinFnToFnPtr：核对唯一外部叶ID、
BuiltinAttr、prvalue形状及精确函数/指针签名，不按名字赋予语义。返回域转换、
无写和正常返回协议仍独立要求。509项CPU测试、49项Clang专项及demo通过。

固定完整vLLM TU、400万预算、原显式非负int域和ABI/effect协议下，blockIdx.x
getter现在得到条件checked；检查实现前后hash一致。仅解除该wrapper的值保持/
条件无写义务，不包括receiver求值、实际launch域、循环体或整核，原vLLM整体
仍unknown。未运行GPU，未新增holdout成功。原始报告及边界见
`.agents/handoffs/wb04-builtin-callee-20260922.md`。

## 完整 TU getter 预算与下一处拒绝

固定 vLLM 完整 AST 实测 3,705,324 个节点，目标 getter/leaf 各唯一，超过默认
100 万节点预算。现允许显式配置至 1000 万的扫描预算，默认不变；仍扫描完整
TU 并严格检查声明唯一性，不抽取子树替代。失败报告保留 effect 协议哈希。
506 项 CPU 测试及 demo 通过，48 项 Clang 专项测试通过；无 GPU 执行。

400 万预算的完整 TU 诊断到达具体调用后，因 BuiltinFnToFnPtr 返回
unsupported_callee_cast，未得到 checked；没有因增大预算而放宽语义。
诊断使用显式非负 int 域与 32 位 ABI，不声称这些已从实际 launch 恢复。
下一步核验该 builtin 转换的支持条件，再处理 receiver、launch 及 body 组合。
详见 `.agents/handoffs/wb04-getter-full-tu-20260922.md`。

## Getter 条件无写检查与 builtin lowering 诊断

getter_returns 新增 check_no_memory_write：fresh 值域检查通过后，要求显式外部
无写/正常返回前提精确绑定 root、start 和 leaf；证据引用只记录为 unverified。
这是依赖叶值域及 ABI 的更窄充分条件，不是独立 effect 分析，不能虚构值域来通过。
503 项 CPU 测试及 demo 通过，包含真实 Clang signed leaf→unsigned wrapper 正例、
写入及不透明调用负例。未改变 body 门控，未运行 GPU。

固定完整 vLLM AST 的 blockIdx.x getter 是 static 单 return，外部叶声明返回 int；
同工具链 CUDA 编译诊断得到 llvm.nvvm.read.ptx.sreg.ctaid.x 的 memory(none)。
这是外部语义依据的局部观察，不按名字或 ConstAttr 自动认定无写，也未给完整
vLLM TU 签发 checked。大 TU 预算、调用点 receiver、实际坐标域和 body 组合仍待建立。
详见 `.agents/handoffs/wb04-getter-effects-20260922.md`。

## 同 ID launch 归一化与实际 body 首拒绝定位

launch_facts 对同root、同非空ID且完整节点一致的重复出现归一化，site保留
ast_occurrences；不同ID不合并，缺ID逐次保留，同ID内容冲突整体unknown且sites为空。
函数定义唯一性不放宽，归一化不证明执行次数或host可达性。真实Clang lambda回归
及配置/target冲突负例已通过，496项CPU测试通过。
完整vLLM重放每个具体实例由4次AST出现变为1个site（ast_occurrences=4）；另一个
CUB头内kernel_not_exact_declref仍保留在unresolved_sites，不视为整TU launch闭包通过。
body首拒绝已定位：float的blockIdx.x PseudoObjectExpr，Half/BFloat16的operator float
CXXMemberCallExpr；未放宽调用/属性副作用假设。报告新增body未知范围及源有效性前提。
详见 `.agents/handoffs/wb03-launch-identity-20260922.md`。本轮无GPU，适配链未完成。

## 直接坐标循环的独立 body 保持检查

coordinate header observed 后现调用原副作用白名单，保护 induction、边界和
两个精确 receiver 声明；不放宽任何调用/未知节点。安全小例建立两个条件 body
保持标志；改变量、隐藏引用、改边界或不透明调用保留 not_established，并记录
body_effect_reason。父循环仍 unknown、step 为空、header 标志 false；下游组合
仍拒绝。491项CPU测试通过，新增变体纳入既有真实Clang参数化测试。

重放完整 vLLM TU：float两循环因 unsupported_body_effect、Half/BFloat16四循环
因 call_in_body 未建立 body 保持性。launch分析每个具体实例得到同一launch ID的
四次AST出现，不是四次实际launch；当前唯一性门控不能直接消费。原源码block
配置为std::min(hidden_size,1024)，尚未自动检查该构造。下一步需明确这些源码
障碍，不能把名称当API或将重复AST出现当独立执行。本轮无GPU，详见
`.agents/handoffs/wb03-coordinate-body-20260922.md`。

## 完整 vLLM TU 声明绑定与 unsigned 条件递推

固定 c1cafce 恢复实现，用原样 vLLM TU、旧 include/工具链及环境宏重采集完整
device AST，不拼接编译实例。5456 个依赖已观察；三种具体实例的六个循环均能
观察 coordinate header，消除了旧过滤 AST 缺 getter 声明的障碍。父循环仍
unknown，launch/坐标/ABI/body 未建立；不是新 holdout 成功。约5.3GiB AST 本地
保留，索引见 `benchmarks/intake/vllm-rmsnorm-development-full.json`。

现有 column_coverage 新增独立 unsigned compound 条件检查：显式同位宽
int/unsigned int、起点0..B-1和步长B下，检查初值、加法、赋回和末次增量，再复用
覆盖算法。超范围保持unknown；未接源码组合门控，不升级上述vLLM循环状态。
491项CPU测试及demo通过，含小位宽逐步模拟对照；无GPU执行。下一步将同TU
精确getter/receiver、实际launch和ABI连接到该检查，不能由header观察自签通过。
见 `.agents/handoffs/wb04-unsigned-columns-20260922.md`。

## 直接坐标 header 观察与下游拒绝回归

column_loops 保留完整起点/增量 AST，新增受限 coordinate_header_observation：
严格连接 unsigned 属性 getter、receiver 和 unsigned += computation type，
但不填 step、不建立 header/body 递推，父报告仍 unknown。真实 Clang 的改名
property、body 修改、额外窄化和步长算术回归，以及不 mock 循环/launch 恢复的
column_domain 拒绝测试已补齐（线程前提仍为手工测试 fixture）。486 项 CPU 测试通过。
重放固定 vLLM attempt-06 的六个循环均仍 unknown：symbol-filtered AST 缺唯一
getter 声明，value_link 为 callee_declaration_not_unique。未拼接其它 AST，未新增
holdout 成功、GPU 或候选证据。下一步先补同 TU 声明可见性，再检查坐标/launch/ABI
条件下递推；不能仅凭新字段宣称关系恢复完成。见
`.agents/handoffs/wb03-coordinate-header-20260922.md`。

## 完整 standalone TU 重采集与下一语义边界

固定 0dfbbaf，用 source 入口在完整 HIP standalone TU 上重跑 required 依赖观测和
driver trace；两个列循环 step256、局部贡献、归约链、行前缀及输出后缀仍恢复成功。
22 个实现文件哈希与运行后源码一致；320 个依赖文件、7 个计划 bitcode 已记录。
新增 `benchmarks/cases/llama-rmsnorm/source-evidence.json` 索引，修正案例 README
过时的“没有自动源码恢复结果”。完整 TU 指手工 standalone，不是原始生产 TU；
无 GPU、整核 checker 或候选生成结果。0dfbbaf 远端 run35731336147 success。

下一语义边界已按 vLLM 固定 AST 核对：直接 threadIdx.x 起点存在 unsigned→int
转换，blockDim.x 步长依赖实际 launch，+= 本身也使用 unsigned computation。
不能仅放开 wrapper 或将 blockDim.x 猜成常量；需要完整表达式和显式坐标/launch/ABI
条件下的值保持检查。现有拒绝结果保留，不把新分析建议记为已支持。
详见 `.agents/handoffs/wb03-full-input-20260922.md`。

## Driver 计划任务证据与 HIP 依赖输出修正

可选 --toolchain-trace 保存独立 -### dry-run 原文，严格解析唯一 cc1 计划任务，
观察后端文件、triple/CPU、resource-dir 路径及显式 bitcode 哈希。多任务或歧义
保持 unknown；不执行日志命令，不宣称实际 AST 进程身份已核验。
真实 HIP device-only 首次核验发现 driver -MF 被忽略，缺清单正确阻断分析；
现改为同次 cc1 -dependency-file/-MT/-sys-header-deps。最终 symbol-filtered
HIP AST collected，依赖 observed（320 个文件），计划任务 gfx1100/Clang23，
7 个 bitcode 文件已记录。失败及成功工件均保留，不是完整源码关系恢复或 GPU 结果。
481 项 CPU 测试及 demo 通过。336add9 的远端 run35730352101 三任务均 success，
不代表本次提交的 CI。完整闭包/冻结快照/实际进程身份仍未建立，WB-03 未完整验收。
详见 `.agents/handoffs/wb03-toolchain-trace-20260922.md`。

## 同次 AST 编译的依赖观测门控

源码分析入口默认 required：同次 Clang 调用生成包含系统头的依赖清单，
记录原始清单、各文件路径/内容哈希及清单哈希；缺失、歧义、文件不可读或源文件
前后哈希变化时不进入分析。低层 AST 采集保留 off 兼容入口，显式关闭不建立
依赖证据。新增真实 Clang 头文件变化、系统头收集和缺清单门控回归。
本地 make check 469 项通过，make demo 通过；无 GPU 执行，未核验本提交远端 CI。
这只是编译后依赖内容观测，不是冻结输入快照或完整编译闭包；wrapper 实际后端、
resource-dir/SDK 及 bitcode 完整绑定未建立（计划任务观测进展见上节），closure 标志始终 false。详见
`.agents/handoffs/wb03-dependency-binding-20260922.md`。WB-03 仍未完整验收。

## 第二仓库源码验证：vLLM RMSNorm首次评估为unknown

冻结04c01e4分析器，固定vLLM v0.6.6/f49777ba源码及Apache-2.0许可，未改kernel
或分析器。原样生产TU在隔离PyTorch2.5.1头环境及显式CUDA include/配置宏下，
host/device-only两视图均取得symbol-filtered AST。device视图的float/Half/BFloat16
三个实例共6个循环均在起点IntegralCast(unsigned threadIdx.x→int)返回
unsupported_value_wrapper；未到达后续步长/归约/组合检查。模板不是新增案例。
这是一个不同仓库候选的具体拒绝记录，不是holdout通过或CUB语义结论。
前四次环境失败保留；无GPU执行。来源、冻结规则和结果见
`benchmarks/intake/vllm-rmsnorm{,-result}.json`及对应protocol.md。
同次 AST depfile 观测已接入（见上节）；下一步 driver trace 绑定，
不用另一次预处理输出冒充冻结输入。历史 vLLM 工件未因此追溯获得依赖证据。

## 引用类型别名与induction存储期修复

在fe844b0同一真实Clang AST上重放，确认using/typedef/嵌套引用别名仍错误
recovered。现以共享声明类型分类修复引用初始化及写入目标：优先解糖类型，
缺失/未展开证据unknown，不依赖DeclRefExpr值类型，也不扩大循环头类型支持。
induction仅支持自动存储期，static/thread_local拒绝。457项CPU测试通过，含
真实C++与CUDA组合负例、真正using Value=int与只读cast正例；CPU witness确认
三类别名引用512/768、值别名768/768、static与thread_local各3/768。
原HIP AST两个循环仍recovered，最终工件在
`artifacts/wb03-alias-fix-3zAPau/final/report.json`，实现hash前后一致。
另通过GitHub API核实fe844b0的run35522009044三个job均success；不是本次修复的CI结果。
未运行GPU，WB-03仍未完整验收。详见
`.agents/handoffs/wb03-declaration-alias-fix-20260921.md`。

## WB-03 验收状态与P1修复

WB-03是受限源码分析MVP，部分WB-04条件检查已接通；不是完整研究验收通过。
独立谱系留出验证、完整原始生产TU处理与完整编译输入依赖绑定仍未建立。

已在6f947ec复现审阅指出的循环体效果漏洞：真实Clang AST的引用转换、C-style
引用转换、逗号左值和汇编四变体均错误recovered。修复改为存储目标分类及节点
白名单，未知效果保守拒绝，区分header观察与body保持状态，下游列域checker
必须同时获得保持证据。当前四变体均unknown，普通下标写入保持支持；原HIP
AST两个step256循环亦继续recovered。451项CPU测试通过，含不mock循环/launch/
guard恢复的Clang→column_domain_check组合正负例（线程报告仍是外部fixture
前提），及实际CPU执行512/768漏列witness。未运行GPU。
CI新增显式Clang18任务并记录版本，尚未核验该远端任务结果。Polygeist总结与
corpus输入版本状态已同步；O1九输入通过来自既有记录，不是本轮重新实测。
详见 `.agents/handoffs/wb03-body-effects-fix-20260921.md`。

## 最新组合门控：两处行偏移的整数关系

row-prefix保留完整offset/update AST；独立row_offset检查符号乘积恰为row*count，
逐节点核对显式ABI下的整数范围与转换。row_offset_check从同AST fresh组合行坐标、
线程起点和列数域，不消费生成器自报关系。444项CPU测试通过，Sol实现独立checker
并只读审查组合；同范围错误乘积、窄化、可能溢出与绑定错配有回归。
最终真实工件 `artifacts/wb04-row-offset-bLZgDu/final/report.json` 条件checked：
row[0,7]、count[1,1023]下两处整数偏移均为row*count，范围[0,7161]；src实现hash
运行前后一致。新ABI示例的long64为外部假设，不是本轮设备测量。未运行GPU，
指针加法、分配/访问边界、别名、参与和浮点仍未建立；G1/G2/G3不因此整体通过。
详见 `.agents/handoffs/wb04-row-offset-20260920.md`。

## 最新组合门控：row初始化式与grid域

row_coordinate_check从同AST fresh恢复grid域、row-prefix及初始化式结果调用，
在显式group-id叶协议下检查getter和row初始化转换。无需手工提供row声明ID或
上界。428项CPU测试通过，包含getter/初始化窄化、错绑定与非法grid维度回归。
真实工件 `artifacts/wb04-row-coordinate-0WHtJN/report.json` 条件checked，row域[0,7]，
src实现hash运行前后一致。区间是跨grid域过近似，不代表每次launch的row/nrows
相关性；指针偏移、分配范围、调用点有效性和参与仍未证明，无GPU执行。详见
`.agents/handoffs/wb04-row-coordinate-20260920.md`。

## 最新条件检查：grid域与block-id协议来源

grid_configuration和grid_domain_check从选定launch的第0构造配置、字段轴协议及
fresh host guard检查一维正grid域；421项CPU测试通过，真实AST得到x[1,8]、y/z1。
固定SDK头与精确AST追踪确认block getter调用group-id叶(axis0)，HIP7.1.1官方
Index built-ins协议用于明确的外部语义绑定。诊断runner据grid上界派生[0,7]，
补齐前缀getter协议后两个body均条件checked，不再靠人工任选上界。
工件在 `artifacts/wb04-grid-domain-6J9DFi/`；外部实现/normal return、调用点求值、
内存与参与仍未证明，无GPU作业。该协议组合尚为诊断runner，不宣称通用自动
block-id识别。见 `.agents/handoffs/wb04-grid-domain-20260920.md`。

## 最新条件检查：前缀 getter 函数体返回

getter_returns成功报告记录有限返回链的conditional completion；entry_call_check
按同AST/kernel绑定的显式外部正常返回协议逐项检查前缀getter body。缺少契约时
保留其它局部结果但整体unknown，值保持失败不误报为不终止。409项CPU测试通过。
真实工件 `artifacts/wb04-entry-calls-7LiwN4/report.json` 中local-id getter条件checked，
block-id getter缺协议为unknown，因此整体unknown；未凭函数名补全缺失协议。
调用点求值、循环体有效性、helper到达和收敛仍未证明，无GPU作业。详见
`.agents/handoffs/wb04-entry-calls-20260920.md`。

## 最新条件检查：入口前缀循环的有限迭代次数

列区间checker成功报告增加逐线程最大迭代次数；entry_loop_check从同AST fresh
恢复列域与归约入口义务，按精确loop/call范围连接有限递推上界。404项CPU测试
通过，Sol只读审查未发现循环论证。真实工件
`artifacts/wb04-entry-loops-4ITPxL/report.json` 条件checked：列数[1,1023]、步长256
下每线程最多4次，最后一个线程最多3次；末次增量无溢出。
这仍以到达循环、循环体正常完成及既有API/ABI为前提；两个调用正常返回义务与
participation未解除，不声称helper可达或barrier收敛。本轮无GPU作业。见
`.agents/handoffs/wb04-entry-loops-20260920.md`。

## 最新源码证据：归约调用前的控制义务

entry_control定位精确顶层helper调用并恢复入口前缀的call/loop义务，接入
reduction_chain与源码入口实现hash清单；不把局部归约匹配当线程参与证明。
397项CPU测试通过，包含真实Clang按tid提前返回时entry_control为unknown的反例。
固定HIP AST恢复出2个getter调用正常返回义务和1个循环终止义务，工件为
`artifacts/wb03-entry-control-ocHj3Y/report.json`，实现hash前后一致。
这些义务尚未解除，participation=not_established，无GPU作业或部署许可。见
`.agents/handoffs/wb03-entry-control-20260920.md`。

## 最新组合门控：同AST共享下标、数组绑定与容量

shared_storage_check先fresh检查坐标及共享下标，再重建调用链、数组实参与选定
launch；核对helper/shared形参、width/block一致后检查同一数组容量，避免混用
不相干的成功报告。388项CPU测试通过，覆盖动态/静态容量不足、绑定错配和上游
短路。真实HIP工件 `artifacts/wb04-shared-storage-QGyPZ1/report.json` 条件checked：
8个float槽需32字节，launch提供128字节；运行前后src实现hash一致。
这不是新GPU结果，也不是整体内存安全证明。单数组偏移0、无其它动态分配、
外部API/ABI、源有效性、别名/同步/参与仍是前提。详见
`.agents/handoffs/wb04-shared-storage-20260920.md`。

## 最新组合门控：共享写入/收集谓词与整数下标

块归约恢复保留四个完整shared谓词/下标AST；shared_indexing在显式ABI和已建立的
group/lane关系下逐线程检查谓词，仅检查对应活跃分支的下标与转换值保持。
shared_index_check先fresh检查同ASThelper坐标，再连接这些表达式；不把结构匹配
当值保持，也不信旧生成报告。381项CPU测试通过，覆盖错误条件、错误索引、截断、
缺失/重复绑定及inactive下标不执行。真实HIP工件
`artifacts/wb04-shared-indexing-vFqOXr/report.json` 条件checked，实现hash前后一致。
它仅覆盖writer lane0→group槽、gather lane<8→lane槽的整数关系；shared容量/
指针、存储值、同步/参与和浮点结果仍未证明。无GPU执行。详见
`.agents/handoffs/wb04-shared-indexing-20260920.md`。

## 最新组合门控：launch列数域与列索引覆盖

column_domain_check从同AST重新恢复launch实参、host guard必要条件区间与列循环，
结合已检查线程起点，检查两个循环在整个列数域[1,1023]的索引生成次数和末增量。
固定starts/stride时只需检查上界，不枚举列数；kernel形参写入/逃逸、非直接循环
和早退上下文不接受。368项CPU测试通过，含小域穷举交叉验证和组合负例。
真实工件 `artifacts/wb04-column-domain-Vh20Ku/report.json` 条件checked，运行前后
实现hash一致，Sol只读审查后明确结论只涉及索引、不是循环体数据贡献。
前端、外部API/ABI、有效执行及线程参与仍是前提；无GPU作业或部署放行。
详见 `.agents/handoffs/wb04-column-domain-20260920.md`。

## 最新组合门控：helper坐标与逐线程索引分解

块归约恢复现保留完整group/lane初始化AST；独立index_partition检查器在显式
坐标锚点/宽度/ABI下逐线程检查除法或余数与转换值保持，不以范围相同代替映射。
block_coordinate_check重新发现同AST中已连接的helper，将两次坐标读取分别
连接到同一外部local-id协议，再检查完整初始化式。355项CPU测试通过，含同范围
错误映射被拒绝、真实Clang保留unsigned外层转换及组合门控回归。
真实HIP工件 `artifacts/wb04-block-coordinates-8Jv9Ru/report.json` 条件checked：
block256/width32下逐点符合group=t/32、lane=t%32，范围分别0..7与0..31。
Sol审查及实现hash核验通过。结论只覆盖两个初始化式；其它转换、writer谓词、
参与/同步/shared访问和浮点关系仍未证明，无GPU执行。见
`.agents/handoffs/wb04-block-coordinates-20260920.md`。

## 最新组合门控：同AST的block、getter与列起点

新增initializer_domain转换链checker与thread_start_check组合API。后者从同一
原始AST重新恢复循环/归约/launch/构造字段/初始化式，用root hash及精确ID绑定
显式轴和local-id协议，从已检查block.x导出getter域，再串接返回和初始化转换。
删除block checker不必要的“起点已使用x”前提，避免循环论证；配置位置、子报告
一维维度与模型大小均有严格门控。342项CPU测试通过，Sol审查修复后确认。
真实HIP最终工件 `artifacts/wb04-thread-start-psY2gK/report-final.json` 条件checked，
列起点域[0,255]；实现hash与运行前后一致。它仅覆盖选定launch的列起点，仍依赖
显式外部API/ABI/运行配置和可信前端，不检查helper内其它坐标或整核等价，无GPU
执行或部署放行。见 `.agents/handoffs/wb04-thread-start-20260920.md`。

## 最新独立检查：getter返回链的条件值保持

新增verification/getter_returns，直接从单TU函数AST检查exact调用链、外部叶实参
与逐级整数转换，不消费return_trace的成功标志。真实HIP getter在显式外部域
[0,255]与ABI下checked；人为扩大到[0,2^32]时返回窄化rejected，反例2^32。
331项CPU测试通过，包含真实Clang、窄化反例、缺ABI、契约不匹配及结构/预算负例。
最终工件 `artifacts/wb04-getter-returns-fVQljU/report-final.json` 实现hash核验一致。
域真实性、外部坐标语义、初始化链与launch的自动组合尚未完成；无GPU执行，
不签发源程序或部署保证。见 `.agents/handoffs/wb04-getter-returns-20260920.md`。

## 最新源码能力：连接属性初始化式与结果调用

新增initializer_value并接入起点证据value_link：在显式Clang结果不变量前提下，
从全部语义child中唯一识别pseudo-object结果调用；严格核对static getter与
三处receiver，保留外层整数转换，不依据getter名字识别线程坐标。
323项CPU测试通过，含真实Clang静态属性改名案例及结构/类型/接收者负例。
最终真实HIP重跑为 `artifacts/wb03-initializer-value-02/`，起点value_link recovered，
转换unsigned int→const int保留未解除义务。接收者纯度、外部坐标含义、
getter返回转换与launch域仍待检查；无GPU运行或部署放行。见
`.agents/handoffs/wb03-initializer-value-20260920.md`。

## 最新源码证据：getter完整表达式与歧义门控

return_trace保留每步完整return/callee AST、调用类型、声明种类/static信息与
中间成员接收者；重复exact Clang ID不再按遍历顺序覆盖，而是unknown。
315项CPU测试通过；真实HIP重跑 `artifacts/wb03-getter-trace-01/` 仍可追踪到
OCKL local-id外部叶节点，完整保留size_t→unsigned int转换。
这不处理不同ID的重声明关系，也未建立pseudo-object值连接、receiver纯度、
外部坐标语义或窄化值保持，无新增GPU执行。见
`.agents/handoffs/wb03-getter-trace-20260920.md`。

## 最新条件检查：block字段与一维线程模型一致性

新增 `verification/block_configuration.py`，在显式launch/构造/轴字段ID绑定下，
重用constructor_values检查实际字段值并比较(block_threads,1,1)，不按字段名或
总线程数猜坐标。字段交换、多维同乘积、错误模型会拒绝；缺绑定或ABI保持unknown。
真实HIP报告在外部轴假设下得到(256,1,1)与模型一致，312项CPU测试通过。
轴绑定仍是外部协议，线程坐标与实际执行语义未证明；本API未自动并入容量CLI或
部署决策。见 `.agents/handoffs/wb04-block-configuration-20260920.md`。

## 最新检查能力：显式ABI下的launch共享容量

新增独立字节表达式checker与共享容量CLI：从第三配置实参的原始AST检查
`32 * sizeof(float)`及整数转换，不默认sizeof结果，不把溢出或未知表达式放行。
在示例显式ABI与恢复结构前提下，真实HIP报告的block256/width32需要8槽（32字节），
launch表达式为128字节，条件容量checked。运行时block、坐标、单数组偏移0、ABI
匹配与别名仍是前提，source_program_checked/deployable均false。
306项CPU测试通过；无新GPU执行。已补上缺失/重复launch ID及存储报告内部一致性
门控，顶层报告显式列出条件前提。见 `.agents/handoffs/wb04-shared-capacity-20260920.md`。

## 最新源码能力：共享数组实参与声明容量证据

归约链新增独立shared_storage子报告：按同AST的调用范围、精确callee/形参位置
连接直接数组衰减与调用前的局部数组声明，保留原始AST、类型和声明范围。
真实HIP首例恢复第二实参对应动态shared数组，extent为空、容量要求launch bytes；
不把width32当作容量。静态extent、普通非shared数组与动态shared分别表达。
295项CPU测试通过，包括参数换序、容量非32、无界数组、非法cast、错误声明ID和
extern-shared带声明长度仍不得推断静态分配。Sol审查意见已纳入。
仍未检查launch字节数、别名或运行时容量，不授权部署。见
`.agents/handoffs/wb03-shared-binding-20260920.md`。

## 最新源码能力：连接累加器与实际归约调用链

新增 `analysis/reduction_chain.py`，从同一AST重新恢复local与可达helper，按精确
声明及实参位置连接local→block→XOR→shuffle，并核对width及列步长/block线程数。
预算不完整、缺少唯一目标或常量关系不一致保持unknown，不根据函数名选择。
真实HIP首例恢复3段链接，width32/block256/offsets16,8,4,2,1；保留21条未解析调用。
292项CPU测试通过，包括真实Clang改名、参数换序、宽度/步长错误与缺定义/预算负例，
以及注入重复候选的歧义拒绝测试。Sol只读审查未发现该有限范围内的实质错误接受。
这仅连接累加器结构；shared实参存储、坐标、launch、intrinsic、收敛与浮点关系
尚未建立，不能生成已验证GPU候选。见 `.agents/handoffs/wb03-reduction-chain-20260920.md`。

## 最新实现：正式记录器支持显式优化级别

`polygeist_frontend.py --optimization-level 1` 可复用已有O1编译配方；API严格接受
整数0–3，默认0不变，命令/报告/pipeline标签一致。非法类型或范围在创建产物前
拒绝，ROCm隔离与未验证状态保持不变。287项CPU测试通过，正式入口实际O1编译
成功；本轮不重复GPU执行，也不将新编译产物继承为已通过数值测试。
见 `.agents/handoffs/polygeist-optimization-recorder-20260920.md`。

## 最新对照：O1 人工 Polygeist 基线通过9个确定性形状

分阶段实测发现O0局部平方和已经错误（输出位型0x100），而load-only与常量输出
正确；捕获的设备LLVM仍保留正确累加PHI。仅改变cgeist优化级别为O1，局部平方和
3×1恢复正确，完整人工RMSNorm也通过原9个确定性形状（3行，列数1/31/32/33/
255/256/257/777/1023），最大绝对误差1.1920928955078125e-7。
同一W7900与冻结数值协议，保留全部O0失败记录。根因尚未唯一定位；O1改变不只
一个pass，不能据此声称已修复某个特定LLVM bug。该路径仍含人工API/存储改写与
本地编译器补丁，不是原版Polygeist或WaveBridge自动候选，也没有性能结论。
见 `.agents/handoffs/polygeist-o1-numeric-20260920.md`。

## 最新设备验收：人工 Polygeist 基线首例出现 NaN，未放行

用户确认继续使用本机 W7900 后，按 run-experiment 流程确认 PCI 0000:53:00.0
空闲并重链 wave 修正后的 gfx1100 工件。首个3行×1列案例正常执行返回0，但三个
输出均为NaN，冻结数值协议拒绝；立即停止其余形状，不改容差、不测性能。
独立诊断副本仅把输出改成归约 total，同样得到NaN；根因仍待定位，不能仅归因
于rsqrt或据此断言上游方法不支持该模式。此路径含人工API/存储改写和本地编译器
补丁，不是WaveBridge自动候选。原手写HIP基线的通过记录不变。
见 `.agents/handoffs/polygeist-first-numeric-failure-20260920.md`。

## 最新静态验收：设备库波宽与两个目标的 metadata 一致

新增 `rocm-device-wave.patch`，在优化前从实际函数 subtarget 选择设备库波宽
常量，未知或混合波宽明确拒绝。Sol 实现、主代理完成增量构建和双目标编译。
同一人工兼容诊断源码在 gfx1100 生成 wave32/常量0，在 gfx90a 生成 wave64/常量1；
两者固定共享128字节，动态符号表无非空未定义项。284项CPU测试通过。
这仍是 logical32 人工基线的兼容性修复，不是自动重新分工或GPU数值结果。
错误分支未做执行注入测试，设备运行尚未执行；下一步重链新工件并按冻结协议验收。
详见 `.agents/handoffs/polygeist-wave-patch-20260920.md`。

## 最新部署前核验：host 链接通过，wave 库配置仍不一致

新增外部polygeist_harness.cpp，复用既有I/O与HIP检查，调用生成的host入口；
没有重写kernel/launch。生成LLVM编译为host对象并成功链接，但未执行。
独立静态审计确认当前HSACO metadata wave32、__oclc_wavefrontsize64实际为1，
OCKL产物保留mbcnt_lo+hi。固定LLVM wave32测试允许该组合，不足以替代配置
一致性与设备验证，因此下一步先修正serializer库常量选择，不运行当前工件。
见 `.agents/handoffs/polygeist-host-preflight-20260920.md`。

## 最新实现：最小 ROCm 栈兼容补丁打通诊断源码的代码生成

Sol子代理实现限定ROCm GPU模块/generic alloca的AS5补丁，主代理审查并完成
三任务增量构建。原cgeist已保留。相同shuffle诊断源码现在生成HSACO，动态
符号表除空占位外无未定义项；gfx1100/wave32、固定共享128字节。
host局部栈回归前后IR逐字节一致，284项CPU测试通过。不是GPU数值结果；
人工API/静态shared副本与编译器补丁必须作为额外适配成本记录。
见 `.agents/handoffs/polygeist-alloca-patch-20260920.md`。

## 最新定位：shuffle 探针的断言来自局部栈地址空间路径

保存序列化前设备LLVM后，独立Clang复现同一BITCAST断言。仅将helper三处
alloca改到私有AS5并用addrspacecast接回原generic指针，LLVM验证与gfx1100
汇编生成均通过；汇编保留OCKL定义及ds_bpermute_b32，静态wave32。
这是人工IR诊断，不是已修复的源码编译链或GPU数值结果。原编译器未改动。
见 `.agents/handoffs/polygeist-private-alloca-20260920.md`。

## 最新诊断：受限 OCKL shuffle 探针在指令选择阶段失败

独立副本使用已有__ockl_readuplane_i32与signed lane差表达logical32 XOR，
float/int位搬运用4字节memcpy。GPU MLIR生成成功，但LLVM/HSACO路径在helper的
AMDGPU指令选择阶段触发BITCAST位宽断言，未产出IR/HSACO；不放行GPU执行。
条件整数路由枚举2560项通过，仅覆盖声明前提，不证明库或实际机器执行。
详见 `.agents/handoffs/polygeist-ockl-shuffle-20260920.md`；下一步定位地址空间/
位搬运降级，不将该断言直接解释为shuffle语义不支持。

## 最新诊断：显式 OCML 调用可消除 rsqrt 未解析符号

在独立静态shared副本中人工声明并调用__ocml_rsqrt_f32，同一cgeist后端生成
HSACO成功；动态未定义符号只剩shuffle。固定共享128字节、gfx1100/wave32
元数据不变。这是数学API/设备库链接诊断，不是自动math.rsqrt恢复，也未验证
数值等价。原案例与编译器均未改动，没有GPU执行。
见 `.agents/handoffs/polygeist-ocml-rsqrt-20260920.md`；下一步单独验证受限
shuffle兼容路径，不能把普通映射补全当关系恢复的创新。

## 最新对照：静态 shared 修正容量，但未打通后端

固定静态shared[32]诊断副本在同一ROCm工具链两阶段均退出0；GPU MLIR为
memref<32xf32,3>，HSACO固定共享空间128字节，原输入为4字节。
两者仍有相同未解析shuffle/rsqrt符号，host动态共享大小仍为0；未执行GPU。
已同步共同案例能力表，避免保留“Polygeist从未执行”的过时总述。
详见 `.agents/handoffs/polygeist-rocm-static-shared-20260920.md`。

## 最新实测：ROCm 构建完成，真实案例产出 HSACO 但未通过部署前提

完整构建3895/3895退出0，原session29377已结束。首个执行因找不到HIP动态库
退出127；显式设置既有SDK的LD_LIBRARY_PATH后，原host adapter的GPU MLIR
及LLVM/HSACO路径均退出0。不是只能检查host路径了，但也不是适配正确：
HSACO仍有未解析`__nvvm_shfl_sync_bfly_f32`和`__nv_rsqrtf`，固定共享空间
仅4字节，生成host launch的动态共享大小为0。绑定kernel的静态元数据为
gfx1100/wave32，不能代替实际执行波宽。没有加载或执行该工件。
完整证据见 `.agents/handoffs/polygeist-rocm-first-artifact-20260920.md`。
下一步用静态shared诊断副本分离容量问题与未解析通信/数学符号，不宣称G1通过。

## 最新实测：固定前端遗漏动态共享内存 launch 参数

仅将真实host adapter的动态共享请求由128改为256字节，使用同一固定cgeist
及头环境重跑，输出与原IR逐字节一致。CGCall.cc两条CUDA launch构造路径
均传dynamic shmem=nullptr；原输出也没有该operand。这是固定版本/路径上的
信息遗漏，不是跨线程分析创新或完整工具不支持的结论。没有执行GPU。
后端构建仍继续；详细证据见
`.agents/handoffs/polygeist-launch-bytes-20260920.md`。

## 最新门控：ROCm 编译阶段与设备副作用分开记录

共同案例记录器新增显式ROCm路径和AMD目标，绑定三份设备库及LLD哈希。
区分GPU MLIR请求与LLVM/HSACO序列化请求，不凭退出成功升级正确性保证。
禁止该入口启用cuda-lower，并清理alternatives相关环境、设置设备可见性掩码；
掩码不等于沙箱，不能保证编译器没有设备API副作用。284项CPU测试通过，
新增测试是编排mock，不是GPU证据。完整ROCm构建会话29377仍在运行，
最近观测1572/3895；不启动重复构建。下一步待构建结束后检查真实共同案例。
详见 `.agents/handoffs/polygeist-rocm-stages-20260920.md`。

## 最新推进：独立 ROCm 后端已开始真实构建

独立patched Polygeist worktree仅应用已记录的wrapper头兼容和字段断言补丁，
配置host/AMDGPU、Clang/LLD/MLIR及ROCm后端成功。使用项目自定义HIP target
映射和已验证LLVM16设备库；原前端构建/源码不改。实际3895任务构建已启动，
会话29377，尚未完成，不宣称cgeist ROCm可用。首个配置因主代理误写host
编译器路径失败，保留于build-01；成功目录为polygeist-rocm-build-02。
具体路径、命令和继续方式见 `.agents/handoffs/polygeist-rocm-build-start-20260920.md`。

## 最新门控：LLVM16 设备库可读性已建立

固定ROCm Device Libs 5.3.3提交cc06f706，在隔离副本仅将prepare-builtins的
C++14改为17，使用既有固定LLVM16工具构建opencl/ocml/ockl成功（547任务）。
三份bitcode逐个在opaque-pointers=0下verify通过，联合llvm-link后也verify
通过；不再依赖不可读的LLVM23设备库。没有GPU或gfx1100 code-object保证。
官方没有5.3.4标签，不能称原论文环境精确复现。下一步独立配置完整ROCm
后端；命令/失败/哈希见 `.agents/handoffs/polygeist-device-libs-20260920.md`。

## 最新门控：属性字段审计通过，设备 bitcode 不兼容

隔离编译期审计覆盖wrapper实际复制的42个字段：CUDA11.8与当前HIP头的
尺寸及C++类型一致；runtime导出其引用的hipGetDevicePropertiesR0600。
这不证明字段值语义、未映射字段初始化或完整ABI。另一方面，固定Clang16
实际读取当前LLVM23产出的ocml.bc失败（Unknown attribute kind 106）。
完整后端不能直接复用这些设备库；下一步准备兼容设备库，再配置独立ROCm
构建。证据和配置依赖见 `.agents/handoffs/polygeist-backend-prerequisites-20260920.md`。

## 最新验证：ROCm wrapper 的兼容编译

固定Clang16配现有HIP SDK，原wrapper先因缺CUDA头失败，补齐CUDA11.8后
因surface/texture全局类型冲突及缺memcpy声明失败。纯HIP诊断可生成bitcode，
但明确不替代CUDA→HIP能力。隔离副本仅补cstring并临时重命名冲突CUDA类型后，
完整wrapper生成并重新读取typed-pointer bitcode，保留设备属性适配函数。
兼容补丁已记录，上游checkout干净；没有建立字段ABI/语义、链接或GPU执行。
完整后端仍待构建，详见 `.agents/handoffs/polygeist-rocm-wrapper-20260920.md`。

## 最新诊断：LLVM 输出与 GPU 后端分离

执行记录器新增显式 `--emit-llvm`、输出类型及独立 `.ll` 工件名，不提升保证。
静态shared副本实际执行 `--cuda-lower --emit-llvm` 返回255，失败在未消除的
conversion cast，未输出LLVM IR；不能用这条默认host路径判断完整ROCm后端。
282项CPU测试通过。下一步建立固定版Clang及ROCm wrapper构建前提，保留已
构建前端和失败工件；不以CPU化执行代替目标GPU适配。详见
`.agents/handoffs/polygeist-llvm-attempt-20260920.md`。

## 最新诊断：动态 shared 与 shuffle 分开追踪

原adapter的独立副本仅将extern动态shared改为32元素定长shared；实际默认及
cuda-lower均输出IR。lowering分配从1变为32，原0～7访问的容量矛盾消失；
外部NVVM shuffle及警告保持。原launch动态字节数未改，因此副本增加了静态
资源，不能作等资源性能比较或自动适配结果。详见
`research/polygeist-static-shared-diagnostic.md`。无新GPU执行，G1未通过。

## 最新验证：完整 launch 适配与实际 Polygeist IR

新增有父源码/补丁/协议哈希的人工 host adapter，保留三计算函数、域守卫与
完整 launch，仅移出 IO/容器/设备管理。使用全函数选择，默认 O0 和
`--cuda-lower` 均生成包含计算体的 IR；只选 host 入口则遗留 kernel 声明，
不作为成功案例。lowering 后发现共享 memref 容量为1，但存在索引1～7的
访问；shuffle 仍为外部 NVVM 调用并伴随未发射 builtin 的警告。
这不证明正确重定向，也不足以宣布方法级差异；下一步隔离动态共享存储和
shuffle 的实际处理边界。280 项 CPU 测试通过，无新 GPU 执行。
详见 `.agents/handoffs/polygeist-adapter-ir-20260920.md`。

## 最新验证：兼容头文件已接入，暴露 host 前端边界

项目隔离安装 CUDA runtime/nvcc 11.8.89、cuRAND 10.3.0.86，并提取 Ubuntu
libstdc++-11-dev 11.5.0 开发头，未替换系统 SDK 或运行库。实际重试消除了
此前 texture/宏错误；完整输入仍在 host C++ 对象处理阶段断言，未得到 IR。
两次仅选择 kernel 的诊断返回 0，但输出均为空 module，不能算转换成功。
下一步保留计算函数和完整 launch，单独建立有补丁记录的 host adapter，隔离
文件 IO/容器驱动，继续同例能力检查；不是删除 launch 后宣布适配成功。
详见 `.agents/handoffs/polygeist-compatible-headers-20260920.md`，G1 仍未通过。

## 最新验证：Polygeist 构建完成，实际共同输入受环境阻断

固定论文版本的前端构建完成，3296 个任务、退出码 0；随后独立构建
`clang-resource-headers` 成功。已真实运行两次完整 CUDA 输入（`--function=*`），
均未产生 MLIR。首次缺 SDK 库目录；新建同版本 runtime 的 lib64 视图后，
安装识别通过，但出现 Clang 16 / CUDA 12.1 texture 头错误，以及 GCC 13
标准库与 CUDA `__noinline__` 宏冲突，随后工具断言退出。
这些是当前环境接入失败，不是子组模式不支持的证据，G1 仍未通过。
命令、原始诊断、二进制及报告哈希见
`.agents/handoffs/polygeist-first-execution-20260920.md`。
未修改分析实现，未运行新 GPU 实验；下一步建立兼容头文件环境后重试同一完整输入。

## 最新实现：CUDA 块级归约结构

严格支持 barrier callee 位置的 `BuiltinFnToFnPtr`，保留转换和原 callee AST，
不放宽普通参数/值表达式。真实源码重跑 `artifacts/wb03-cuda-block-01/` 自动
发现一个 width32 XOR helper 与一个 block256 七阶段块级归约，精确 reduce
声明 ID 对应；坐标、barrier、intrinsic 和浮点语义仍未建立，checked/deployable=false。
273 项测试通过，AST/源码/实现哈希复核一致。Polygeist 同一构建会话仍在运行。
另修正执行记录：O0 不等于 identity translation；资源头路径核实为 `16.0.0`。
交接见 `.agents/handoffs/cuda-block-callee-20260920.md`。

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

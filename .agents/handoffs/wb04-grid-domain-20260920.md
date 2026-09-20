# Grid 域与 block-id 外部协议交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`0d52114`。
- 用户约定：中文，直接commit和阶段性push，不建PR、不合并master。
- 进展：上轮缺block getter协议而整体unknown。本轮新增独立grid_configuration及
  fresh grid_domain_check，从host guard和构造字段推导grid域，不猜硬件上限或坐标。
- 分工：Sol实现独立grid checker及7项测试；主代理实现组合及5项测试、真实验收，
  Sol只读审查通过，主代理补配置位置0与fresh ctor ID的mock调用断言。
- 验证：`make check`421项CPU测试通过；最后测试断言增强后定向5项再次通过；
  `git diff --check`通过。未知、条件域反例与实际坏launch严格区分。
- 命令1：`PYTHONPATH=src python3 artifacts/wb04-grid-domain-6J9DFi/check.py`。
  grid条件checked，x[1,8]、y/z[1,1]。精确block getter `0x2d2b9db8` 追踪至
  外部 `0x2d2b6d10` (__ockl_get_group_id)，参数0。
  report.json SHA256 `1b76bc238b7438db3c45d8ebfdc4419c42f664414c177db821480cd944db67c3`。
- 本机固定SDK `artifacts/toolchains/sdk-view-sx4rmd37/include/hip/amd_detail/amd_hip_runtime.h`
  252–255与307–310行连接blockIdx.x→wrapper→group_id(0)，文件SHA256
  `a9029bfcb459afd45bcd6851c7b5b9d7995d5e5a6542888684cb5b194155a789`。
- 外部语义依据：[HIP 7.1.1 Index built-ins](https://rocm.docs.amd.com/projects/HIP/en/docs-7.1.1/how-to/hip_cpp_language_extensions.html#threadidx-and-blockidx)，
  2026-09-20核查。该规范给出blockIdx维度范围0..gridDim-1；固定SDK调用对应与
  规范组合为外部协议，不是对OCKL实现或实际运行的证明。
- 命令2：`PYTHONPATH=src python3 artifacts/wb04-grid-domain-6J9DFi/complete_calls.py`。
  从已检查grid上界减1派生[0,7]，并沿用已有local协议；两个前缀getter body
  条件checked。completion-report.json SHA256
  `3b5e542305329b5603c5bda395c1a68d15fe40a5ced19646c5c6a2ddea251677`。
  协议在completion-protocol.json，root/grid/SDK/ABI绑定和src实现hash前后一致。
- 原AST路径/字节hash：artifacts/wb03-initializer-value-02/ast.json，
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
  大工件仅本地保存；源码/协议文档/测试/交接入Git。
- 未执行：新HIP编译、GPU、性能、自动候选或整核等价。
- 局限：域为必要条件过近似；ABI/实际launch/外部group-id语义与正常返回为显式
  假设，未证明receiver、调用点求值、循环body内存有效性和参与收敛。协议构造
  尚为诊断runner，不是通用自动API识别，source/deploy保持false。
- 下一步：把row初始化式连接到该域并检查转换/前缀指针算术，连接声明的数组输入
  范围；不可因为getter body通过就声称kernel全线程可达归约。

# 原始构造实参与字段域交接

- 日期：2026-09-22；分支 `wb03-source-ast`，基线 `ed87f1f`；中文回复，直接
  commit/push，不创建 PR。基线远端 run35744746160 三任务 success。
- 新入口：`wavebridge.constructor_source_check.check`，完整 TU 中按唯一直接
  构造表达式 ID fresh 恢复身份、实参和完整字段映射，不消费调用方的成功报告。
  GPT-5.6 Sol 实现；主代理写真实 fixture/tests，审查并运行全量/完整 TU 验收。
- Literal/default 从原始子树取值，核源码/参数默认关联、cast 链、括号类型、
  prvalue 和无额外子节点；动态实参按原始表达式 ID fresh 运行 minimum checker。
  统一核实际实参/形参类型，再核字段初始化转换；不重复计算已检查的动态实参转换。
  参数全 TU 唯一，字段映射精确位置/ID/类型绑定。只有全部字段成功才设置 fields。
- 不改旧 `constructor_values.check`，不篡改原始 AST 或把前端 unknown 改成
  inspected，不将动态值伪造为 literal 或虚拟变量再交旧 checker。
- 实际验证：`make check` 553 项、`make demo`、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'`
  86 项均通过；`PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest
  tests.test_source_constructor_clang` 8 项通过，无 skip。
  系统 AOCC Clang 17、ROCm Clang 23；`git diff --check` 通过。
- 负例：错误 minimum、额外构造写入、copy、负数到 unsigned、缺/多/错域、
  伪造 checked、源码条件分支变更、重复参数 ID、默认类型及字面量 wrapper 畸形。
  正例包括动态+默认 7/13、多个动态参数和字段交换；不按字段名字猜坐标轴。
- 保证范围：只覆盖构造求值时的条件整数字段域。输入域、ABI、源有效性和
  引用/临时量生命周期是显式前提；不验证外围清理、命名对象保持、copy、实际
  launch 或 GPU 行为。没有新 GPU 作业、性能结果或独立 holdout 成功。
- 完整 TU 重放：`PYTHONPATH=src python3 artifacts/wb04-source-constructor-WTYBO5/run.py`；
  报告 `artifacts/wb04-source-constructor-WTYBO5/report.json` 的 SHA-256 为
  `1721005815920334c0db556fee1d260e438cb8f5d4af5313f78b9570b76e7326`。
  输入固定 AST 文件 SHA-256
  `5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f`，root canonical hash
  `97da57a94da3614db2fb47dd9dfffedf135015512dbb75da015c2c3f04ccf433`。
  显式 400 万节点预算，307.52 秒；八个实现文件前后哈希一致。
  原构造 `0x3b006d38`，动态实参 `0x3b006cc8`；给定 hidden_size
  `0x3b005a58` ∈ [1,4096]、int/unsigned int32，组合 checked：字段
  `0x248faab8`（x）∈[1,1024]，`0x248fab20`（y）=1，`0x248fab88`（z）=1。
  原始 constructor_arguments.status 仍 unknown，未改写为 inspected。
  这里仅显示实际字段名称，不凭名称将其解释为硬件轴；没有把投影当完整 TU。
- 下一步：在真实输入上建立构造对象到 launch 配置的关联与保持义务，并单独
  将 hidden_size 的源 API/合法输入域连接到外部协议；不可直接把诊断域当实测域。

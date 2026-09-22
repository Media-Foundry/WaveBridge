# 交接：命名 launch 配置的构造身份边界

- 日期、分支、基线：2026-09-22，wb03-source-ast，46a9625；中文回复、直接 commit/push。
- 本轮推进：检查真实 vLLM host 配置到 launch 的首个断点；不是重新提供人工 block 大小。
- 源码障碍：launch 第二配置实参为复制 `block` 的 CXXConstructExpr，而旧入口只
  接受 CXXFunctionalCastExpr 的 conversionFunc。原 block 初始化还包含 min 调用
  和缺少源码子节点的默认实参；不能直接视为已验证配置。
- 实现：constructor_arguments 新增受限 direct 构造身份关联；沿精确 alias ID、
  RecordType.decl ID、唯一完整 record 及其唯一选定 ctorType 定位构造函数。
  不按 dim3 名称匹配，拒绝基类/模板成员/using、复杂 alias 链和重复 ID。
- 依据：LLVM 17 JSONNodeDumper 的 VisitCXXConstructExpr 从已选择的
  getConstructor()->getType() 写 ctorType。此前是 explicit conversionFunc，
  新模式是派生关联，constructor_identity.mode 明确区分，不伪称原 AST 自带引用。
- 保证：inspected 仅为身份/实参证据。标量字段关系仍经已有独立 checker；copy/
  move 字段、命名变量在使用前不变、捕获语义、实际 launch 域均未由此建立。
  每次身份扫描默认 100 万节点，显式上限 1000 万；不是总资源限制。
- 分工：主代理实现与真实 Clang 回归；用户指定 Sol 子代理诊断完整 TU 和只读复核。
- 实际测试：make check 531 项通过、make demo 通过、64 项 Clang 专项通过；
  新增同名不同 namespace 正例、copy 保持 unknown、默认来源缺失、未知调用、
  错 alias/record/signature、重复 ID、模板/继承和预算负例。
- 完整 TU 命令：`PYTHONPATH=src python3 artifacts/wb03-vllm-launch-diagnostic/run_complete_tu.py`。
  原 AST SHA-256 `5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f`；
  3,705,324 节点，显式身份扫描预算 4,000,000，三个实现文件前后 hash 一致。
  报告 `artifacts/wb03-vllm-launch-diagnostic/complete-tu-result.json`，SHA-256
  `24c01beaf9d18fa79415e1ea0b5f2d20c296faf3b10afae0fe2f2847899085d2`。
  runner 直接读完整 TU，不消费仅用于定位的 projection.json。
- 真实结果：launch `0x3b0199f8` 的 copy 表达式 `0x3b018528` 精确关联到
  构造 `0x2499bad8`，参数是 block `0x3b0060f0` 的 symbolic 引用；field recovery
  为 unknown/field_initializer_not_exact_parameter_reference，value checker unknown。
  block 原始表达式 `0x3b006d38` 关联到三 uint 构造 `0x248fae38`，三个字段映射
  recovered，但 min 调用与两个默认实参缺源码使 arguments/value 均 unknown。
  没有构造出人工字段值，也没有新的实际 launch 配置 checked。
- 后续定位证据：host hidden_size `0x3b005a58` 来自 TensorBase::size(-1) 的
  long→int 转换；block 和 hidden_size 在分派 lambda 中均按引用捕获。
  min callee `0x3b0067a8` 的完整定义为两个 const int& 形参上的单 return
  ConditionalOperator。主代理核对真实投影：比较是 `__a < __b`，true 返回 __a，
  false 返回 __b。不可将它口述成 `(b<a)?b:a`，相等时引用身份不同；本轮尚未
  检查此返回关系，仅记录下一支持子集。projection SHA-256
  `7032cbcdd85e1981eb0f16fb6e6df97d92dfec2c9409ac5619e36678a6f273ec`。
- 历史 CI：46a9625 run35740192321 success，不代表本轮提交 CI。
- 未执行：GPU、候选生成、性能实验、新谱系验收、整核验证。
- 下一步：根据实际 min 定义恢复受限引用选择关系，再检查复制字段及 block/
  hidden_size 在初始化到 lambda launch 之间的保持；不能跳过按引用捕获义务。
- 提交安排：完成完整 TU 复核后提交并推送当前分支；大工件保持本地忽略。

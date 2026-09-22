# 交接：对象使用与构造期逃逸边界

- 日期/分支/基线：2026-09-23，`wb03-source-ast`，`230d0f2`。
- 用户目标：继续原始构造至配置复制的值保持链；中文回复，验收后直接提交推送。
- 完成：从固定完整原生 TU 清点词法源对象全部函数内引用与闭包父表达式；
  新增 `constructor_escape.cpp` / `test_constructor_escape_clang.py` 的真实
  编译、现有检查器组合与 CPU 执行回归。Sol 只读核查既有构造检查保证范围。
- 原始输入：`artifacts/wb-vllm-native-Rw42Hh/ast.json`，SHA256
  `c4642860faadf8920de29c3e79ca8dc984cd88af0e5ede7ce3f6de18b02c4d45`。
  诊断命令 `PYTHONPATH=src python3 artifacts/wb-source-uses-nGKMyR/inspect.py`；
  脚本 SHA256 `eda27031cf34526a2e2920b74b9d9cc4eed1c57cecc45b993f0ced0f9053e16c`。
  报告 `artifacts/wb-source-uses-nGKMyR/report.json`，SHA256
  `87cdbcede6f8813212e94ae59cd071a1cbfc523b73f4aca20044dc39dc6176d8`，34.54 秒
  （不含起始输入哈希核对）。scope 是整个所属函数，跳过 lambda closure record 重复 body。
- 使用观测：源 `0x38e43f10` 有 7 处显式 DeclRef。4 条为原生捕获初始化，
  另外 3 条分别进入复制 `0x38e56348`、`0x38e5bfa8`、`0x38e61b88`。
  三个 dtype 分支都在清单内，不只包含已选 float launch。
- 闭包调用形状：下列 lambda 都位于 MaterializeTemporaryExpr → NoOp cast →
  CXXOperatorCallExpr 接收者位置；表为诊断候选，尚未签发调用/逃逸结论。

  | lambda | operator call | callee 声明 |
  | --- | --- | --- |
  | `0x38e671e0` | `0x38e67478` | `0x38e51ec0` |
  | `0x38e58010` | `0x38e582a8` | `0x38e55e40` |
  | `0x38e5dbf0` | `0x38e5de88` | `0x38e5bb50` |
  | `0x38e637d0` | `0x38e63a68` | `0x38e61730` |

- 反例：无发布版本 CPU 返回 3；构造器 body `published=this` 或字段初始化
  `publish(this,value)` 后，调用独立 mutate 函数，复制结果均为 99。三种调用方
  都只有一个显式 source DeclRef（复制实参），所以调用方引用扫描不能证明无写。
  原有 constructor_source_check 对两个发布版本保持 unknown，record_copy_check
  对三种复制仍局部 checked 且 source_object_preservation=not_established。
  本轮是组合边界回归，不是已发现现有源码检查误放行。
- 验证：`PYTHONPATH=src python3 -m unittest tests.test_constructor_escape_clang`
  默认 Clang 17 与 `PATH=/opt/rocm/llvm/bin:$PATH` Clang 23 均 3 项通过。
  启用 VKdLhn 插件/AOCC17 环境的 `make check` 586 项无跳过、`make demo`、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'` 119 项通过。
- 仍缺：普通局部对象/record/constructor 精确形状下的构造期不发布地址检查；
  所有捕获闭包的接收者与调用声明绑定、逃逸检查；所有相关复制和隐式操作的效应。
  不能直接把现有 constructor_source_check 的 checked 政名为 no-escape。
  构造会写目标字段，“不发布地址”也不能叫“无写”；构造后与析构阶段另行处理。
- 未执行：GPU、性能、部署、真实对象历史值保持证明；诊断 report 保持 observed_not_checked。
- 下一项：用真实的上述立即调用形状与无发布构造子集建立受检查的规则，保持
  不透明调用、别名转换、成员/基类隐式构造和未知效果保守拒绝，随后再组合值域。
- 提交状态：本轮新增测试与证据记录，验收后推送当前分支，不创建 PR。

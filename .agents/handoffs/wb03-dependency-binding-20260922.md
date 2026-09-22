# 交接

- 日期、分支和基线：2026-09-22，`wb03-source-ast`，基线 `27a0ad0`。
- 用户目标：继续补齐源码输入证据；中文回复，直接 commit，验收后推送当前分支，不创建 PR。
- 已完成：`frontend/dependencies.py` 严格解析单条 Clang depfile，保存原始清单、
  路径和文件哈希；`clang_ast.collect` 增加可选 required 模式，同次 AST 调用
  输出包含系统头的依赖清单；`source.run` 默认 required，缺依赖证据不分析。
  required 模式禁止调用者覆盖依赖选项或传入未展开 response/preprocessor 参数。
  低层采集默认 off 保持兼容；显式 off 仅用于诊断，不获得完整输入证据。
- 实际验证：最终 `make check` 469 项全部通过（4.353 秒），`make demo` 通过，
  `git diff --check` 通过。真实编译器为 AMD Clang 17.0.6 / AOCC 5.1.0。
  新增 12 项测试包括清单解析、缺文件、源变化、别名路径、真实系统头收集、
  用户头内容变化及 source 门控；缺清单门控用 mock 注入观察失败，其余真实
  Clang 正例直接采集，不把故障注入称为真实工具故障。
- 实际 CLI：

  ```bash
  PYTHONPATH=src python3 -m wavebridge.source tests/fixtures/column_loops.cpp --compiler clang++ --compiler-arg=-std=c++17 --symbol columns --int-bits 32 --output-dir artifacts/wb03-dependency-binding-dRvS8I/source
  ```

  返回 `analyzed`，依赖状态 `observed`。`report.json` SHA-256：
  `8fd2c7745a75179f7b824ded406f81d79b70391c6f75bdc477466d3e0dcf29c0`。
  原始工件本地保留且不入 Git；这是真实 Clang CPU fixture，不是生产 ML/GPU 结果。
- 未执行：GPU 作业、完整 HIP 工具链重采集、远端 CI 核验、性能测量。
- 保证范围：只观察编译结束后的依赖内容，不排除编译期间并发修改；depfile 不是
  完整闭包证明。`frozen_snapshot`、`compilation_input_closure_established` 始终 false；
  `checked`、`deployable` 仍 false。旧 AST 工件不追溯升级。
- 提交计划：本交接与实现、测试、状态一起提交并推送当前分支；具体结果以 Git 为准。
- 下一项：记录 wrapper 实际执行后端及 driver/cc1 trace、resource-dir 和显式
  bitcode 文件哈希，保留多编译视图与不能解析时的 unknown；不以另一次 -E 输出
  冒充同次 AST 的冻结输入。独立谱系成功与 WB-03 完整验收仍未建立。
- 阻塞：本次 CPU 验收无阻塞。

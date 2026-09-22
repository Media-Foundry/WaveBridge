# 交接：捕获来源边界

- 日期/分支/基线：2026-09-22，`wb03-source-ast`，`53ab8e6`。
- 目标：继续关联复制实参的运行时来源；中文回复，验收后直接提交推送。
- 完成：扩展 `tests/fixtures/record_copy.cpp`，实际执行按值、按引用、外值内引用
  三条路径。源初始化 x=3、闭包构造后源 x=99，返回分别为 3、99、3。
  `WAVEBRIDGE_CAPTURE_EXECUTION` 条件 main 逐项核对，不使用 NDEBUG 可禁用的 assert。
  AST 回归确认三种局部复制关系仍 checked，但 source identity/history 均未建立。
- 验证：`make check` 563 项、`make demo`、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'` 96 项通过；
  默认 Clang 17 与 `PATH=/opt/rocm/llvm/bin:$PATH` Clang 23 下
  `PYTHONPATH=src python3 -m unittest tests.test_record_copy_clang` 均 10 项通过。
- 本地接口核查：AOCC 5.1.0 安装目录的 `include/clang/AST/DeclCXX.h:1076`
  提供 `getCaptureFields`，明确从捕获变量映射到 closure FieldDecl；文档明确
  init-capture 不加入该映射，合并 lambda 可有多个变量对应同一字段。
  `LambdaCapture.h` 提供 getCaptureKind/getCapturedVar；`ExprCXX.h` 的
  capture_init_begin 文档关联第一个捕获初始化与第一个字段。
  这些只是可用 API 证据，尚未实现或验证 native collector；不能当成 JSON 中已有精确边。
- Sol 只读核查：Clang 17.0.6/23.0.0git 的按值、引用、混合与嵌套 JSON 中，
  closure 隐式字段没有 source VarDecl/capture initializer/body DeclRef 的直接 ID 边；
  initializer 和 body 的 referencedDecl 仍指词法声明。多个同类型捕获无法仅靠
  类型或名字唯一配对。没有将字段顺序观察升级为新的运行时身份保证。
- 没有执行：GPU、完整生产 TU 重采集、数值域传递或新 holdout 验收。
- 保证边界：没有升级现有 checker；执行反例说明最内层 by-reference 不足以追溯
  原始对象，所有外围 capture 与对象生命周期/写入历史必须分别检查。
- 下一项：用原生 Clang 精确捕获 API 提供同次采集的字段/变量/捕获模式关联，
  连同嵌套路径和编译输入绑定；先覆盖本次三个反例，拒绝 init-capture 等未支持情况。
  不通过字段名称、源码 offset 或不同编译进程的裸指针 ID 猜测连接。
- 提交状态：本轮测试及记录随验收提交；远端 CI 按对应提交核对。

# 交接：复制求值时的字段关系

- 日期、分支与基线：2026-09-22，`wb03-source-ast`，基线 `67387bf`。
- 用户目标：继续源码关系检查，中文回复；验收后直接 commit/push，不创建 PR。
- 完成：`record_copy_check.py` 从完整 TU fresh 检查实际构造的逐字段整数复制；
  真实 Clang fixture/回归及协议、状态同步。Sol 子代理实现，主代理补充回归与验收。
- 实际验证：`make check` 562 项、`make demo`、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'` 95 项通过；
  `PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest tests.test_record_copy_clang`
  9 项通过。本机默认 Clang 17，ROCm Clang 23。
- 没有执行：GPU、性能测量、新的生产源码采集或新 holdout 验收。
- 完整 TU 重放：`PYTHONPATH=src python3 artifacts/wb04-record-copy-p0wp2b/run.py`，
  163.77 秒；输入 `artifacts/wb03-vllm-full-ERL83Q/ast.json`，SHA256
  `5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f`。
  原始表达式 `0x3b018528` 的四个完全一致出现归一；构造 `0x2499bad8`、
  参数 `0x2499bc78`、字段 `0x248faab8/0x248fab20/0x248fab88` 得到同字段关系 checked。
  词法源声明 `0x3b0060f0` 不代表已经解决捕获与运行时来源。
  报告 `artifacts/wb04-record-copy-p0wp2b/report.json`，SHA256
  `f3e257d3650d4954f4bd98cbce4e87a6e975fde5b78992133ff27b3d4e58ccdc`；六个实现
  文件运行前后哈希一致，checker SHA256
  `82a3beb015b0a61717d666fcd444c12aed545cb7203754a17415dcb2d731f82b`。
  这些大型本地工件被忽略、不入 Git；属于既有 vLLM 开发案例重放而非新增 holdout。
- 保证范围：实际复制实参的同字段整数值关系。词法 DeclRef 不是运行时对象身份，
  按值捕获也不得转移原始对象数值域。源对象有效且字段读取有定义仍为前提。
  `source_object_identity`、`source_object_preservation`、`launch_semantics` 未建立；
  `source_program_checked=false`、`deployable=false`。
- 下一项：精确关联 lambda 捕获与运行时对象来源，再检查初始化至复制的无写路径；
  不得仅因局部复制 checked 就组合初始化字段域或宣称 launch 已建立。
- 提交状态：本文件随本轮验收提交；远端 CI 状态以该提交对应工作流为准。

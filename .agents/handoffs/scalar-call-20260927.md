# 完整单标量调用效果交接

- 日期、分支、基线：2026-09-27，wb03-source-ast，0c03e50；开工工作区干净。
- 约定：中文，验收后直接commit/push当前分支，无PR，不合并master。
- 完成：scalar_call_effects组合checker、scalar-leaf-effect-assumption/v1协议、
  真实Clang回归、固定softmax完整调用回放和证据说明。
- GPT-5.6 Sol负责5项真实Clang测试及只读复核，无阻断问题。
- 验证：匹配native插件make check，1024项/67.822秒，无跳过；demo/diff通过。
  固定回放checked，inputs_unchanged=true，命令/哈希见experiments实录。
- 未执行：GPU、生产TU重采、远端CI核验。
- 范围：完整单个调用条件无写。外部leaf实现和evidence reference未验证；
  不解除初始化/存活/边界/FP值、整核或部署义务。循环门控未变。
- 提交：本轮上述文件直接commit/push；无用户改动混入。
- 下一步：把此类fresh报告接入独立条件循环恢复，保持外部前提标签、未知
  父报告及嵌套循环保护；再检查真实softmax剩余拒绝，不开放动态break。
- 阻塞：本轮无。

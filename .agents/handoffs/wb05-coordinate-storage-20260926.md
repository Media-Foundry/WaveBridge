# 坐标声明存储期修复交接

- 日期、分支、基线：2026-09-26；wb03-source-ast；fc67639，初始工作树干净。
- 用户要求：中文、直接 commit 后推送当前分支，不创建 PR，不合并 master。
- 完成：row_prefix 的直接 row/start 声明只支持普通自动 const int、无 TLS/属性；
  thread_start_check 独立从同一 AST 核对完整声明唯一、kernel 直接块作用域及
  相同存储规则。没有改变通用 initializer_evidence 的调用证据语义。
- 回归：source.run + 真实 Clang 的四个 static/TLS 变体均 unknown；普通版本
  recovered。真实 CPU witness 普通变量两次 0/1，static/TLS 0/0。
  thread 组合测试另外覆盖属性、重复身份、全局和嵌套起点；组合其余恢复仍是 mock。
- 验证：匹配 native 插件环境下 make check：802 项通过，64.983 秒；make demo
  和 git diff --check 通过。Sol 子代理只读复核未发现阻塞问题。
- 工件：artifacts/wb-coordinate-storage-0TCnEI/，含 reproduce.py、真实源码/AST、
  comparison.json 与 tests-final.log。比较是在同一 AST 上调用 fc67639 原始
  row_prefix 模块及当前实现；不是历史全部依赖的隔离重建。
- comparison.json SHA256：42b99e79474c0766e63aa9ef4265de34e5e338808523d7f8be898ea29130c512。
- 未执行：GPU、HIP 重新编译、性能测量。C++ 反例不等于 HIP 设备缺陷。
- 保证范围：declaration_evaluation 仅说明每次经过自动声明时的初始化规则，
  不证明必达、getter 无副作用、跨源码入口值/叶值对应或整核正确。
- 下一步：在完成自动存储期核验的基础上，将 local_structure 角色同本次 fresh
  prefix、thread、row/count 证据精确连接；保留 input 内容及运行实参对应义务。
- 提交/推送：由主代理验收固定真实 AST 重放后统一执行；不提交本地大工件。
- 固定真实源/候选 AST 双侧重放退出 0，仍 evidence，局部模板相同、叶值对应
  not_established；实现哈希前后稳定。完整报告保存在
  artifacts/wb-local-structure-hfn1Di/report-coordinate-storage.json，SHA256
  a5e413eae13fb261252b98c9e6f0ba2e07d53197802e28d4eebd4fb6542ce0f7。

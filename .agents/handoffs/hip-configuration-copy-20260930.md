# 交接：条件字段与精确配置槽绑定

- 日期/分支/基线：2026-09-30，wb03-source-ast，8b0f13b；开始工作树干净。
- 用户目标：持续推进完整源码适配门控；中文回复，直接commit并定期push，不开PR。
- 完成：launch_binding新增fresh组合，所选槽自动决定copy；核对copy目标
  同一配置call/callee/position。保留模型、API、运行时和部署未验证边界。
- 测试：新增合成CUDA host-only全链fixture，不mock恢复器。Clang23专项4项
  23.256秒、Clang17专项4项28.005秒通过；最后补充hash/conditional断言后，
  冻结make check共1386项293.843秒无跳过通过。demo/diff通过，Sol复核无阻断。
  日志/tmp/wb-config-copy-{tests,clang17,check,demo}.log。
- 真实重放：artifacts/wb-hip-configuration-copy-20260930-01/report.json，SHA256
  766d587f53aba0678442e554f506eeeecadb0d6a9aa9310c2055320e3b47967b。
  同一冻结native输入；完整22copy，字段32/4/1，launch/configcall/position1
  均精确绑定。完整命令、输入/实现hash见experiments/hip-configuration-copy-20260930.md。
- 未执行：新GPU/HIP程序与性能实验；完整Clang23捕获专项兼容性未补齐。
- 范围：条件模型内所选槽字段，不是API维度解释、全部配置、实际运行时
  alias来源、源码整体或GPU部署证明。WB-03和G1研究验收仍未全部成立。
- 提交：本交接与代码直接提交并推送当前分支，不合并master。
- 下一步：连接已有配置API/整数ABI协议下的字段角色与实际block维度，再与
  device侧线程/列关系核对；不得把位置1或字段名本身当作API语义证明。
- 阻塞：无本轮实现阻塞；真实API/运行时前提是仍需明确处理的部署义务。

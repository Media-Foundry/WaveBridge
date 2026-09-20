# kernel 实参域与G1核查交接

- 日期、分支和基线：2026-09-20，`wb03-source-ast`，`bb575ef`。
- 用户约定：中文；直接本地commit，不开PR、不推送。
- 主代理使用research-lit技能定向核实Polygeist/CKTI；技能使本轮同时记录
  论文、固定源码、访问边界与待执行矩阵，而非把环境不可用当语义不支持。
- Sol子代理实现 `verification/kernel_arguments.py` 和测试；主代理完整审查、
  补指针/浮点/错误类型/输入不变覆盖，并独立验收真实报告和全仓测试。
- 已完成：单个可信位置绑定的标量整数域转换检查；不是完整kernel签名检查。
- 未执行：新增源码编译或GPU运行、Polygeist构建/同例变换、CKTI运行。
- 保证边界：显式域、ABI、原始AST和位置绑定可信仍是前提；整核与部署未知。
- 交付：代码、测试、协议、研究记录和本交接直接提交；本地产物不公开发布。
- 下一项：准备保留通信结构的共同CUDA输入与固定Polygeist构建，同时继续
  连接列数域到列循环/行偏移义务。G1仍未通过，不扩写创新性主张。

## 实际验证与产物

主代理 `make check`：244项通过。`git diff --check`通过。

真实源码报告输入：`artifacts/wb03-source-launch-guards-01/report.json`。
显式ABI：`examples/abi/int32-conditional.json`。
输出：同目录 `kernel-argument-domains-01.json`，以独占新文件保存，不覆盖旧证据。

主代理通过 `PYTHONPATH=src python3 -` 执行API编排：先确认site的
`parameter_binding_status=bound_by_position`，以
`configuration_check._host_guard_assumptions`核对报告/launch/位宽元数据，
再对全部4项调用 `kernel_arguments.check`。依
`normalization_output.count_parameter_id`而非参数名字选取列数参数。

实际状态按position为unknown/unknown/checked/unknown。position2的区间为
[1,1023]，单个LValueToRValue转换保持int32值；两个指针没有适用整数域，
浮点叶不在支持范围。证据整体为partial，所有source/deploy标记false。
输出绑定原始报告字节、ABI字节，以及kernel_arguments、integer_conversion、
configuration_check实现hash。本轮没有改动源码报告或原始kernel。

先前工作实际GET、源码hash、版本及PATH查询结果见
`research/baseline-checks-20260920.md`。仅进行了只读公开资源查询，不曾
构建或运行对照方法；没有联系作者或向外部账号发送消息。

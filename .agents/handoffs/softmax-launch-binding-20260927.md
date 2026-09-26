# 交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，6f667af；中文回复，直接提交推送。
- 实际进展：复用 `launch_binding.check` 于同一 native AST，预选 kernel 的
  唯一 launch、4 个配置槽位、8 个形参位置绑定 checked。新 driver 为
  `experiments/softmax_launch_native.py`，不消费旧成功报告。
- 工件：`artifacts/wb-softmax-launch-native-VU50pj/report.json`，SHA256
  `64f13be67f51ff19673b1fbc8b72e23840e8718238a4ca52ed546aeec0f6f4db`；
  inputs_unchanged=true，完成后实现逐文件哈希核对一致。
- 身份：kernel 0x30d762e0、launch 0x30d76610、config callee 0x2e3828b0；
  block slot1 0x30d75650 是 threads VarDecl 0x30d69b78 的复制。完整 TU
  另有22个未解析launch位置，不当作已解决。
- 验证：8项已有真实Clang launch-binding测试通过（0.137秒），demo/diff通过。
  6f667af 的远端 CI 36280680885 completed/success；未改checker，无GPU。
- 尚未建立：配置字段值、source-object历史、host可达性、launch/API语义、
  完整lane多重集与store参与性。getter `[0,31]`不是完整坐标族。真实warp_size
  API只有声明，不能由函数名/目标名称直接给32；物理warp映射另需证据。
- 正在运行：pointer-history exec session **67233**，日志与报告
  `artifacts/wb-softmax-pointer-history-0KgDSq/{run.log,replay.json}`。本交接时
  仍live，仅protocols_bound，未取得终态。主src与其driver冻结，禁止因
  observation timeout或ps不可见重启。必须从原handle核验。
- 子代理：getter_review 正在只读查看可用于threads对象的最小现成检查入口；
  不应扩展成另一套host框架。其后续消息/诊断结果需与本报告分开登记。
- 下一步：取得pointer重放终态/哈希；从实际threads复制源与host API出发，
  逐项解除字段值/历史/参与义务，不能输入手写starts后宣称自动完整覆盖。

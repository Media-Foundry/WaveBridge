# 宽度显式用途与目标条件检查交接

- 日期/分支/基线：2026-09-26，wb03-source-ast，31264af。中文，直接commit/push；无PR/master合并。
- 实现：GPT-5.6 Sol新增analysis/width_uses.py与6项单测；主代理新增4项真实Clang方法及重放/完整性脚本。完整TU按fresh block/XOR共同width声明枚举精确DeclRefExpr，五类角色按位置分类，其余包括printf均unknown。声明/stub/表达式类型与身份、未知cast、别名解糖、预算和深树边界保守处理。
- 保证：只覆盖显式引用，折叠/省略引用未覆盖，转换与改写安全未证明。所有checked/source_program_checked/deployable=false；不接入部署，不为生成器签发许可。
- 验证：make check 766项通过（57.981秒），Clang专项260项通过（54.425秒），make demo退出0；匹配AOCC17 native插件启用。专项开发中两个reason期望曾对调并失败，修正后10项专项和上述完整验收通过。
- 工件目录：artifacts/wb-width-use-target-PrXkck/，width.py、target.py、receipt.py及各自JSON/log；CPU/Clang/demo日志均保留。本地大工件不入Git。
- width重放：源AST f0114e85794b328b2d9be4796b0fdbd6dee270164c87548b0d7beeaedadd1f25，目标AST 37927fb111d065114f8681e4f57eb9d719a08163fc47a13d5eaf9a207edf0a89。两侧均6个显式引用、五类各1和external_other1，unknown(explicit_width_uses_not_fully_classified)。host额外引用源码offset3688；没有因未调用或诊断而豁免。width.json SHA256 1245b769b71ca9eba27e82e305de2ab69fba13043b27042c914e331279a13a04。
- 目标协议：使用新kernel 0x2d98d930、launch 0x2d9c96e8、ctor 0x2cfa5cc0、轴字段0x2cfa58f8/5960/59c8及外部leaf 0x2d8598e8/0x2d85a300，手工绑定明确API/ABI假设，非自动语义推断。target-protocol.json SHA256 dbbd17e9f5be95aa0b024ad903c6af5ffc0786fcb62860713daefae97a083b15。
- 目标检查：collect_rmsnorm从新目标AST fresh调用，147.618秒完成，顶层evidence、integers=evidence、output_structure=recovered、xor_routes/block_routes=checked。width64/block256、offsets[32,16,8,4,2,1]，shared需求4 partial/16 bytes、可用128 bytes/32 float槽；barrier是外部条件，不是证明。target.json SHA256 562616f09f1ec2a4eb838e5a01c4a06b39819ef5bdcbc50fa390d905e7d2fc74。
- 只读审查：Sol确认未复用源成功报告或旧ID；指出target.py仅按外部声明总数断言不足以建立逐ID唯一性。正式运行结束后receipt按Counter每个ID恰1并核kind，实际通过；明确属于post-run audit，不包装成preflight。81个实现文件前后/当前哈希一致。src冻结解除。
- 会话：width13340、target18766、全测95898、Clang61827均退出0；无遗留进程。demo单独退出0。未重采AST/重编译/运行GPU。
- 实现SHA256 e06aad73cf091952e96ff3a9f5bef334c295723c49dbec9b4121082b2a3aa783；单测f3fd9c7b780e028a64e44963e310db9140b9837e7d5a3a34776880c3c9322ac8；真实Clang测试ff775515725abbbed1fa68741b12cefa553b1d8db68c51c65ab852c23273f3c6。
- 下一步：明确host诊断的允许观察差异与剩余引用覆盖，再建立源目标关系门控；不靠忽略external_other或将折叠用途缺失解释为无用途来放行。同步/参与/intrinsic/FP与实际wave64未建立，继续禁止native64 GPU执行；原logical32数值证据不迁移。
- 提交/推送：实现、测试、compiler/analysis说明、status与本交接直接提交当前分支。未检查本提交远端CI。无阻塞；研究独立谱系与强基线差异门槛仍未完成。

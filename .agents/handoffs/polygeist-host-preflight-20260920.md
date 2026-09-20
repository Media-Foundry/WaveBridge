# 交接：外部 host harness 与部署前静态核验

- 日期/分支/基线：2026-09-20，wb03-source-ast，f0dbc2c；中文，直接commit，无PR/push。
- 按run-experiment技能先核对环境/设备执行前提；根规则无明确服务器配置，
  已异步询问是否沿用本机W7900。尚未启动GPU，未添加W&B或外部通知。
- 新增experiments/baselines/polygeist_harness.cpp，复用原HIP baseline main的
  输入检查、设备身份输出、分配/复制、同步和文件输出。改为调用生成的C入口，
  不重新构造kernel或launch；资源描述要求外部工件，不伪称dynamic shared128。
  使用者必须外部验证协议/设备/产物，harness不自动签发正确性。
- 实际编译：固定build-02/bin/clang -c -x ir -O0 -fPIC
  artifacts/polygeist-frontend-awqe6wf1/output.ll，得到
  artifacts/polygeist-host-link-K2KTmc/generated.o。
  AOCC clang++ -std=c++17 -D__HIP_PLATFORM_AMD__，SDK include/lib及
  libamdhip64.so.7与rpath，链接harness.cpp+generated.o成功；同目录compile/link.log。
  未运行可执行文件；其global constructors会注册GPU工件，不能当无副作用命令测试。
- 静态审计绑定HSACO hash33ec479b：kernel metadata为wave32，rodata地址0x7c8
  的__oclc_wavefrontsize64字节为01。OCKL helper含mbcnt_lo、mbcnt_hi、63边界和
  ds_bpermute；库配置与kernel metadata不一致真实存在，不能凭符号全解析放行。
- 固定LLVM llvm/test/CodeGen/AMDGPU/wqm.ll的GFX10-W32检查也出现lo+hi序列，
  因此不把hi指令本身宣称为已证明的错误；gfx1100硬件行为/收敛仍缺实测。
  delta的同logical32结论依赖lane正确，不能从整数枚举反推实际lane。
- 完整反汇编：artifacts/polygeist-frontend-awqe6wf1/disassembly-complete.log。
  初次输出经head截断导致管道141，保留在disassembly.log；后续完整重跑退出0。
- 未执行数值/性能/加载，未修改冻结tolerance。当前是人工baseline兼容诊断，
  不是WaveBridge自动候选或native64优化。
- 下一步：让serializer设备库波宽常量匹配实际TargetMachine波宽，保留旧产物，
  增量构建后重查metadata/rodata/lane指令；满足前提并确认设备后再做受控数值验证。

# 交接

- 日期/分支/基线：2026-09-30，wb03-source-ast，b52417f；开始时工作树干净。
- 目标/约定：持续推进，始终中文，直接commit、稳定后push当前分支，不建PR。
- 插件扩展：完整非依赖EnumDecl的底层/提升类型、位宽/符号、fixed/scoped与
  named constant十进制值/ID；top ast_int_bits。同次AST ID，非穷尽非runtime域。
- 匹配插件：artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so；
  artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so。
  Clang23两个旧API构建失败日志保留，最终isDependentContext版本两版构建通过。
- 实际原TU：artifacts/wb-hip-native-enum-20260930-01/native.json，SHA256
  fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4；collected，
  inputs_stable=true，未修改harness，无probe forceinclude，334依赖、206枚举。
- 新身份：wrapper 0x3b52b8d0，param 0x3b52b7c0，typedef 0x3a80ae48，enum
  0x3a807358；underlying uint32/promotion int32；success 0x3a8074a8值0。
- 验证：完整1330项/98.193秒无跳过；启动后新增唯一性断言的23/17各3项专项
  重跑通过；demo/diff通过，Sol复核无阻断。/tmp/wb-native-enum-check.log。
- 未建立：高层driver消费新metadata、API成功/输出效果、runtime域、完整转换
  语义、整核/部署。没有GPU/程序运行。scoped enum的promotion非null不代表允许隐式转换。
- 下一步：在新工件中fresh绑定query/guard的精确转换与enum metadata，不能复用
  旧AST ID或只凭名字绑定。旧固定driver继续使用旧工件，直到显式更新选择协议。
- 详见experiments/hip-native-enum-evidence-20260930.md及docs/contracts.md。

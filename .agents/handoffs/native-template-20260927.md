# 交接：模板实例原生证据缺口

- 日期、分支、基线：2026-09-27，wb03-source-ast，8601ed5；起始工作树干净。
- 用户约定：中文，直接commit并推送当前分支，无PR，不合并master。
- 实际发现：旧native的r 0x19538580没有local_record_objects观测；没有
  将缺失解释为无析构。原计划生命周期checker改为先补真实前端证据。
- 完成文件：capture_plugin.cpp启用模板实例遍历、新增constructor_calls；
  native_captures.py与插件README同步限制；新选点driver、5项真实native
  测试、实验实录与状态。没有新增生命周期checker或放宽数组门控。
- 验证：新插件AOCC17构建成功；同一PyTorch harness重采collected，固定
  模板规则定位真实Max对象/构造声明；native和选点报告哈希见实验实录。
  最终1095项测试通过，73.200秒，无跳过；demo/diff通过。首轮草稿kind
  断言的6个失败保留check.log，最终通过记录check-final.log。
- 工件：artifacts/wb-native-template-OqD1PQ/{native,selected-object}.json。
  新native SHA256 a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45。
- 精确新ID：caller0x30d762e0，call0x30de0078，helper0x30dc6c48，
  r0x30dcdae0，scope0x30dce648，record0x30d87bc8，ctorExpr0x30dcdb78，
  ctorDecl0x30d88228。实参为空，trivial/default ctor均true；自动存储true，
  has_nontrivial_destructor=false。AST definitionData dtor.trivial=true。
- 未执行：GPU、效果checker重放、远端CI；不是新谱系或生产TU完整验收。
- 剩余：原生trivial标志不单独证明完整初始化、正常返回、存活和实参效果。
  旧工件/旧四项pending结论不变；必须在新AST内重新绑定，禁止混用指针ID。
- 下一步：从新native精确绑定构造声明与record结构，限定支持的trivial
  空对象初始化/销毁子集，补非trivial/错绑/缺证据负例后接入数组检查。
  随后继续shuffle/defaultarg，不推断全局无写或部署保证。
- 提交范围：本轮源码、测试、driver、文档；大型工件不入git。

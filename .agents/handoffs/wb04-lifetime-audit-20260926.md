# 生命周期前提审计

- 2026-09-26，wb03-source-ast，基线f665cd2；源码冻结不变。
- 原v3重放session2874/PID231726仍存活，约6分35秒；未重启，终态仍待收取。
- 与Sol只读复核共同定位：外层source引用闭合不约束copy ctor内部经参数产生
  的析构/重建；当前local_copy_effects在值checker之后且以live/readable为条件，
  不能循环用其checked解除alive。先前“只凭外层引用闭合、作用域和初始化”
  的建议不充分，不予实施。

## 主代理实际复现

本地产物：artifacts/wb-copy-lifetime-cqMQya/{rebuild.cpp,check.py,rebuild,report.json}。
源码SHA256：95d0c9e6e16b742cd357c24299156c5e6dd6397e67d100f637a74b9fafee6b91。
报告SHA256：e01873f307bdfce5a976b455c12957bb7be64fe0b3a3a88254110cf980776ee1。
核心反例：

```cpp
#include <new>
struct Rebuild {
  unsigned x;
  Rebuild(unsigned value) : x(value) {}
  Rebuild(const Rebuild& other) : x(other.x) {
    auto* pointer = const_cast<Rebuild*>(&other);
    pointer->~Rebuild();
    ::new (pointer) Rebuild(99);
  }
  ~Rebuild() {}
};
unsigned f() {
  Rebuild source(3), first(source), second(source);
  return first.x + second.x;
}
```

实际工件用单独DeclStmt及typedef别名以匹配支持子集。命令：
`/opt/AMD/aocc-compiler-5.1.0/bin/clang++ -std=c++17 artifacts/wb-copy-lifetime-cqMQya/rebuild.cpp -o artifacts/wb-copy-lifetime-cqMQya/rebuild`；
执行二进制输出first_plus_second=102，退出0；
`PYTHONPATH=src python3 artifacts/wb-copy-lifetime-cqMQya/check.py`退出0。
使用真实Clang17原生插件AST，初始化checked，source_reference_count=2，
顶层unknown/fresh_direct_record_copy_not_checked；copy原因
copy_constructor_body_or_member_shape_unsupported。当前工具正确拒绝，不是漏洞。
这是一条有限CPU反例与AST检查，不增加全仓测试项数，不是GPU实验。

## 下一项实现边界

先抽出/前移纯结构copy-constructor效果分类，不依赖source字段值或alive假设；
严格检查const-ref形参、空body、直接字段读取、无额外调用/析构/重建/发布地址，
属性及默认参数保守门控。既有字段值checker复用该结构结果，避免重复规则。
只有这项与初始化、顺序、完整引用集合成功组合后，才讨论删除alive协议键。
必须独立处理source/destination在C++抽象机中的对象分离，不能说物理ABI地址
已证明不重叠。不透明调用的非标准栈探测/伪造地址能力仍未建模；普通source-valid
条件不能自动排除所有实现扩展。不得添加value_preserved/noalias同义假设。

本轮只写证据和状态文档，git diff --check；未改src，未运行GPU。下一轮先
收取v3原任务终态与77个实现hash，再开始结构效果重构。

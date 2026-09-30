# 条件对象来源模型与构造到复制的字段保持

状态：受限模型检查，不是目标平台的别名或完整 C++ 验证。

构造字段值与全部显式引用闭合分别成功，不能直接推出真实执行中的值保持。
旧栈地址、跨 activation 保留指针及实现扩展可能绕过当前函数的 DeclRef 清单。
因此新增组合只签发 `unexposed-fresh-automatic-object/v1` 模型内的条件结论，
不将外部模型前提改名成源码已证明的 no-alias。

归纳基是自动完整对象的受检查直接构造：全部标量字段初始化且未发布 this。
归纳步 fresh 枚举同一函数全部引用，要求无 capture、每次仅作读取相同整数
字段的 const-reference 复制，目的对象独立、字段映射完整双射且不发布源地址。
词法顺序与 cleanup 观察须分别 checked，不能仅消费引用闭合的父状态。

模型假设忠实完整 AST、有效顺序执行及指定整数 ABI；排除伪造地址、旧栈
指针、栈探测、异步干扰、非局部跳转和外部生命周期替换。只有在这些假设下，
其他调用、实参及清理代码才不能接触未发布对象。它们仍可改变全局、抛异常或
阻止复制发生；不声称这些代码纯、不声称所有静态复制都执行。

输出区分 selected_source_address_publication_not_observed_in_supported_ast_subset、restricted_object_provenance_assumed
和 runtime_object_provenance_verified（始终 false）；字段保持为 conditional。
只给所选复制读取时及正常完成对应字段初始化的区间，不给后续被调函数内的
目的对象保持、launch API 语义、机器码或 GPU 部署保证。

真实源码回归包括正常多分支复制、显式写入/引用逃逸/析构/汇编/capture、构造
和复制构造发布地址，以及 opaque helper 使用保留指针的模型边界。最后一项
即使条件检查成功，也不能描述为实际程序安全。该假设仍是研究与部署缺口，
不是已解除的完整源码验收门槛。

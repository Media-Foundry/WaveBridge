# 编译器变换

计划根据已恢复关系生成绑定的 kernel/launch 候选，显式处理路由、步长、writer、临时存储和目标能力要求。

当前有 qdot 模型构造，以及 `wavebridge.transforms.source_token.edit` 的窄源码
改写原语。后者输入完整 AST、调用方选定的声明 ID、主源码 bytes/路径/哈希和
目标整数；只接受显式位于主文件的普通 constexpr const int 声明及直接十进制
IntegerLiteral 初始化。宏、头文件、别名、缺失位置和冲突身份返回 unknown。
它按 Clang byte offset 只替换一个 token，返回完整源码和前后哈希，不搜索变量名
或全局替换常量；尚不负责选择语义角色、引用用途闭合或 kernel/launch 关系检查。

成功状态仅为 `generated_unvalidated_candidate`。`checked`、
`source_program_checked`、`deployable` 始终为 false；这是离线提案，不是安全适配。
调用方必须独立重采目标 AST，重新绑定目标声明和 launch，不能复用源 AST 的 ID
或成功报告。W7900 的普通 wave32 证据不能放行 logical64/native64 候选。

生成器不能自行签发检查结论；数据格式常量不能随逻辑宽度一起替换。

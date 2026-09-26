# 离线源码候选与目标重分析交接

- 日期、分支、基线：2026-09-26，wb03-source-ast，b42d0e8。中文回复，用户授权直接commit/push，不开PR、不合并master。
- 实现：GPT-5.6 Sol负责source_token.py与单测；主代理补真实Clang回归、实际生成/重分析脚本、工件串联及文档。原语仅替换精确主源码声明初始化literal，不选择语义角色、不给自己签发检查结论。
- 新文件：src/wavebridge/transforms/source_token.py；tests/test_source_token.py；tests/test_source_token_clang.py。同步compiler/transforms/README.md、docs/architecture.md、docs/status.md和README。
- 范围：完整TU中唯一普通constexpr const int VarDecl，显式主文件loc；单childless prvalue十进制int literal；仅允许隐式CUDAConstantAttr。拒绝宏/header/alias/TLS/storage/未知属性/哈希与位置不一致；AST预算避免无界遍历。所有checked/source_program_checked/deployable=false。
- 验证：匹配AOCC17 native插件启用，make check 756项通过（59.967秒），Clang专项256项通过（54.710秒），make demo退出0；新增13项测试。Sol只读复核未发现阻断问题。未核验本提交远端CI。
- 命令及日志目录：artifacts/wb-source-candidate-1sKytL/。依次PYTHONPATH=src python3 generate.py、reanalyze.py、receipt.py（均以该目录中的完整脚本路径执行）。generate会话33990、reanalyze49950、全测91111、Clang/demo20852均已退出0；无遗留作业。
- 源输入：llama-rmsnorm手工HIP standalone，SHA256 7284151f806d710ff3396b94b62b3ec35d5bef3f44815e1e7837aad66dc85823。完整旧AST SHA256 f0114e85794b328b2d9be4796b0fdbd6dee270164c87548b0d7beeaedadd1f25；旧外部协议79f7871193fe0825586e9b24f544910cf2c34a17f4100fc4a323bc596311fa04仅用于源选点，不搬到目标。
- 实际生成：fresh源静态配对和block/XOR结构恢复共同选width声明0x2ebf1c10，不按kLogicalWidth名字。只改offset486的32→64；block256、launch共享字节、函数名、输入域、epsilon和所有其他bytes未改。候选SHA256 2bf010241f268b2bbc96e77e67a9e888690ee9bd81ae676fdaa80f9072c987cb。generation.json SHA256 f3aff5ec6523f1f485778ee4cb2477e80f0310ccbbed6718e6b79d41da6eb54a。
- 目标重分析：hipcc --cuda-device-only --offload-arch=gfx1100，通过source.run的-fsyntax-only fresh采AST、依赖和trace，不生成机器码/运行GPU。新kernel 0x2d98d930、launch 0x2d9c96e8；静态配对checked，chain/output recovered，width64、block256、offsets[32,16,8,4,2,1]。未用旧pointer ID或成功报告作为目标检查输入。
- 目标AST SHA256 37927fb111d065114f8681e4f57eb9d719a08163fc47a13d5eaf9a207edf0a89；target.json SHA256 914615ff57690dc7cbe8241a382311cfe7218cdfa3cc9dfde1ff8e9cd3fd0f24。receipt.json SHA256 fd7e5c1445c0bc0cb464a68e83aa35b9a4ecba47111966f2090cf74a27ebd0c9。receipt复核仅一个token变化和80个实现文件前后/当前hash一致，源码冻结解除；只是完整性收据，不是语义证明。
- 生成器SHA256 be50a07bbca8c09e349877295c2f72f43f4344f5b6d54b2f19667f6f89b2de34；单测c85bb8e4cee2ca78df7bd56068875063e30f2ec328c0cca4fe17693de7b0f631；真实Clang测试70cfa33969fcd736a5b662aa894a6888d3201e75fceec246f27eff19be0365c8。
- 尚未执行/证明：全部6处width用途分类（报告明确false）、target外部设备协议重绑定、source-target值关系、参与/同步/intrinsic对应、浮点契约、W7900 wave64模式和数值运行。该提案不是安全适配或WB-05验收，不进入qdot pipeline，不继承旧logical32 GPU通过结论。
- 下一步：先完成width引用用途闭合（不认识就拒绝），再从目标新AST恢复精确API/坐标声明以重建外部协议并调用独立目标组合；native64能力unknown继续阻止GPU执行。冻结后的独立谱系和强基线差异仍待完成。
- 提交/推送：只提交实现、测试、文档与本交接；artifacts大工件保持本地，不上传。无阻塞，无远端/GPU作业。

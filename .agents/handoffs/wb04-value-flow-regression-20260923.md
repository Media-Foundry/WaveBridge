# 按值实参跨层回归与下一组合边界

- 日期：2026-09-23；分支 `wb03-source-ast`；基线 `2ba9b4a`。
- 上轮属于实际进展：新参数绑定实现与完整TU证据已提交；CI `35770080069`
  本轮核验success。中文、直接commit/push，无PR。

## 本轮改动

仅修改测试/fixture和文档，不新增checker或提升任何保证。
`object_uses.cpp` 添加会修改按值参数且写全局计数器的callee、普通调用与
立即by-reference捕获lambda两条调用路径，并以按引用改写source作为负对照。
同次原生AST经过真实初始化、引用闭合、捕获、局部效果和参数目标绑定，
没有mock恢复器或checker。测试协议生成由只寻找名为target的VarDecl扩展为
选择源对象的copy表达式，因此真正覆盖配置实参所需的临时copy路径。
capture lifetime/activation仍为显式测试前提，没有宣称自动解除。

独立编译执行同一fixture的CPU main：普通按值后读回3、捕获路径按值后读回3、
引用改写后读回99；全局计数依次1、2、3，表明callee不是纯函数。
静态报告前两项checked且历史保持仍not_established，引用对照unknown。
这是有限CPU观测，非GPU结果、普遍等价或历史保持证明。

## 验收

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
make demo
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
```

649项CPU、173项Clang专项及demo退出0，原生插件测试实际执行；日志在
`artifacts/wb-value-flow-rwFQkI/{tests,clang,demo}.log`。定向11项也通过。
CPU程序编译使用 `-std=c++17 -DWAVEBRIDGE_OBJECT_USES_EXECUTION`，独立运行退出0。
无新完整vLLM重放或GPU执行；当前实现代码未变化。

## 不用同义假设替代待证结论

Sol只读审阅指出：如果协议直接要求no_alias、无未跟踪修改、target非重叠，
可能已经把历史保持主要困难写成假设。下一步应自动关联源VarDecl/DeclStmt/
CompoundStmt与每个copy的外层立即调用语句，检查声明在先及同步嵌套调用链；
控制流和对象生命周期未建立前，不能只比较源文件offset。
同时审计初始化未发布目标地址、所有reference-capture别名的范围，以及精确
按值实参的语言语义；不因多个子报告checked就升级source值保持。

未来对象模型前提需明确C++方言、可信原生元数据与是否排除栈扫描/指针伪造/
非C++内存主体，而不能包含source_value_preserved_assumed、no_alias_assumed、
target_nonoverlap_assumed或opaque_calls_pure_assumed这类替代待证结论的开关。
这是后续设计审查要求，尚不是新定理或已经实现的历史组合checker。

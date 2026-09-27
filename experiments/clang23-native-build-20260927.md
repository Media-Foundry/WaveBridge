# 与实际 HIP SDK 匹配的原生插件

2026-09-27，基线`1619f08`。原生插件C++实现未修改，SDK未修改，无GPU执行。

## 固定来源与生成

SDK的share/therock/therock_manifest.json将llvm-project固定在
`8f497e0992fb7513f7f78a6f6b6f1056c375e961`，patches为空；这与compiler版本输出一致。
在独立工件仓库浅层fetch该提交，稀疏检出llvm、clang、cmake、third-party及libc，
排除测试/文档目录。源码工作区clean。原整仓压缩包下载已明确终止，未用于构建，
不完整文件保留；实际构建来源是Git检出的固定提交，不是截断压缩包。

工件根目录：`artifacts/toolchains/clang23-native-8f497e0/`。
source-git约435MiB，build约62MiB。未安装到系统，未重编译Clang或ROCm。

首次CMake配置因缺少同提交libc公共头失败，记录在configure.log；补取该子树
后configure-libc.log成功。关键配置为Release、LLVM_ENABLE_PROJECTS=clang、
LLVM_TARGETS_TO_BUILD=AMDGPU;X86、LLVM_ENABLE_RTTI=OFF、LLVM_ENABLE_ASSERTIONS=OFF，
关闭LLVM/Clang测试、示例、benchmark和文档。

LLVM_TABLEGEN与CLANG_TABLEGEN分别使用SDK中的llvm-tblgen和clang-tblgen。
执行`ninja -j 4 clang-tablegen-targets intrinsics_gen`，170项生成任务全部完成。
构建只生成开发头并编译WaveBridge插件；保留完整CMakeCache、生成日志和depfile。

固定源码已经检出后，生成命令可重放为：

```bash
WB_NATIVE_WORK=artifacts/toolchains/clang23-native-8f497e0
WB_SDK_LLVM=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm
cmake -S "$WB_NATIVE_WORK/source-git/llvm" -B "$WB_NATIVE_WORK/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=clang \
  '-DLLVM_TARGETS_TO_BUILD=AMDGPU;X86' \
  -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_BENCHMARKS=OFF \
  -DLLVM_INCLUDE_EXAMPLES=OFF -DLLVM_INCLUDE_DOCS=OFF \
  -DCLANG_INCLUDE_TESTS=OFF -DCLANG_INCLUDE_DOCS=OFF \
  -DLLVM_ENABLE_RTTI=OFF -DLLVM_ENABLE_ASSERTIONS=OFF \
  -DLLVM_TABLEGEN="$WB_SDK_LLVM/bin/llvm-tblgen" \
  -DCLANG_TABLEGEN="$WB_SDK_LLVM/bin/clang-tblgen"
ninja -C "$WB_NATIVE_WORK/build" -j 4 clang-tablegen-targets intrinsics_gen
```

## 插件编译复现

以下路径以仓库根为工作目录；不应将这组开发头用于别的Clang版本。

```bash
WB_NATIVE_WORK=artifacts/toolchains/clang23-native-8f497e0
WB_SDK_LLVM=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm
"$WB_SDK_LLVM/bin/clang++" -std=c++17 -fPIC -fno-rtti -shared \
  compiler/frontend/native/capture_plugin.cpp \
  -I"$WB_NATIVE_WORK/source-git/clang/include" \
  -I"$WB_NATIVE_WORK/build/tools/clang/include" \
  -I"$WB_NATIVE_WORK/source-git/llvm/include" \
  -I"$WB_NATIVE_WORK/build/include" \
  -MD -MT wavebridge-inputs -MF "$WB_NATIVE_WORK/plugin-replay.d" \
  -o "$WB_NATIVE_WORK/libwavebridge_capture_plugin-replay.so"
```

最初构建使用默认depfile target，插件成功，但现有依赖观察器要求
wavebridge-inputs而返回depfile_target_mismatch；该记录不算依赖验证通过。
上面的重放使用显式target，另存so、depfile及日志，不覆盖首次工件。
重放依赖清单711项、status=observed；两次插件SHA256相同，为
`329f59bb40a967f0ce6fd4d72876940b7a9e034ebc65aec1e6cc1edd8cd4cf35`。
这不是对所有构建输入的预冻结保证，依赖清单在编译结束后复核。

插件ldd仅列系统libstdc++、libm、libgcc_s、libc等，不链接旧AOCC Clang库。
Clang/LLVM符号由装载进程解析；装载成功不等于一般ABI兼容性证明。

## 验收与实际 HIP 采集

使用新插件和SDK Clang运行test_native_builtin_calls_clang、
test_native_captures_clang、test_native_cleanups_clang，24项通过（0.432秒）。
包括普通/间接调用排除、非空NaN参数及原生绑定冲突等正负例；不是GPU测试。
这不是全套1215项测试在Clang23上的兼容性声明。

```bash
PYTHONPATH=src python3 -m wavebridge.frontend.native_captures \
  artifacts/wb-softmax-hip-pilot-20260927-10/pytorch-softmax-hip.hip.cpp \
  --compiler artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc \
  --plugin artifacts/toolchains/clang23-native-8f497e0/libwavebridge_capture_plugin.so \
  --compiler-arg=-std=c++17 --compiler-arg=-O2 \
  --compiler-arg=--offload-device-only --compiler-arg=-DWB_COMPILED_COOP_WIDTH=32 \
  --compiler-arg=-I/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-softmax-hip-pilot-20260927-10 \
  --timeout 180 --output artifacts/wb-hip-native-20260927-01/native.json
```

会话27998正常退出，status=collected。新工件SHA256：
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
新ASTContext的ID必须重新绑定，不与先前JSON或CUDA工件连接。
原始工件约539MiB，保留本地，不提交Git。

334项采集依赖observed，pilot三份派生源码逐hash一致。payload记录capture=0、
expression_cleanups=367、local_record_objects=277、builtin_calls=1020、
constructor_calls=997；这些数量是非穷尽前端观测，不是执行次数。

选中实例为`0x745c579e5490`；quiet_NaN方法声明为`0x203335e0`，内部builtin
call为`0x20334a68`，native callee为`0x203347a8`，builtin_id=1042，
name=__builtin_nanf，实参ID为`0x20334a98`。全部来自本次同一ASTContext。
GPT-5.6 Sol只读复核确认该callee DRE为prvalue，现有结构检查器可直接支持。
此前JSON工件中观察到的lvalue形态不能推广成Clang23统一行为；本轮没有修改
checker来接受lvalue。两份工件不同形态的成因尚未验证。

主执行者另外在默认100万AST节点预算下fresh运行inspect_structure，对精确
builtin call得到checked；报告为本次目录的builtin-structure.json，SHA256：
`2db09ec3c3abe4fbb9741cbdff816ffa6c0822059140e76db48349454242c623`。
这里的checked仅为原生身份与受限参数结构；value/effect_semantics仍未建立。
make demo及git diff --check通过；本轮未修改生产代码，未重新运行全套CPU测试。

本轮证明的是匹配工具链能装载现有插件并采集实际HIP输入，不是builtin
效果、循环体保持、源码等价或GPU部署证明。compiler/plugin仍属于可信前端。
构建依赖及采集依赖为事后观察，不宣称冻结完整构建闭包。

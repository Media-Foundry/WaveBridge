# Polygeist 兼容头环境与真实输入诊断

- 日期 2026-09-20；分支 `wb03-source-ast`，基线 `30bbf3d`，开始工作区干净。
- 按用户要求中文汇报、直接本地 commit，不创建 PR、不推送。
- Sol 只读盘点：本机旧 libstdc++ 只有运行库，无开发头；不修改 cgeist 的
  LD_LIBRARY_PATH。主代理执行以下隔离准备和重试。

## 依赖准备

```bash
python3 -m pip install --no-deps --target artifacts/toolchains/cuda-11.8-wheels --log artifacts/cuda-11.8-install.log nvidia-cuda-runtime-cu11==11.8.89 nvidia-cuda-nvcc-cu11==11.8.89 nvidia-curand-cu11==10.3.0.86
# 在独占 artifacts/toolchains/gcc11-headers-BTAqay 内执行：
apt-get download libstdc++-11-dev=11.5.0-1ubuntu1~24.04.1
```

两条成功。deb 使用 `dpkg-deb -x` 提取至同目录 `root`，不执行系统安装。
包 SHA-256：`d97c42f258f923a728c6e2268fa557cf6fb3d331b9ced9387d2c024d77816fe7`。
新视图 `artifacts/toolchains/cuda11-polygeist-view-LXjgEk` 的 include/lib64
指向同级 cuda-11.8-wheels/nvidia/cuda_runtime 的 include/lib，bin/nvvm
指向该集合 cuda_nvcc 的对应目录。不是完整 nvcc SDK 或 GCC sysroot。

前端 include 顺序为 gcc11 提取目录下 `usr/include/c++/11`、
`usr/include/x86_64-linux-gnu/c++/11`、`usr/include/c++/11/backward`，
随后 CUDA11.8 cuda_nvcc/include 与 curand/include。仍使用构建的 Clang
16.0.0 resource-dir、系统 C 头和原 cgeist 二进制；未更换运行库。

## 实际记录

全部仍用原始人工 CUDA standalone，源码未修改。完整命令、工具/源哈希、
stdout/stderr 保存在各 report.json。以下路径前缀均为 `artifacts/`。

| 报告 | SHA-256 | 实际结果 |
| --- | --- | --- |
| `polygeist-frontend-z84j9wlb/report.json` | `d030b0b4d81fdb65ceff102eefd5229f029fd9013bbdacbeab40e20f99670158` | CUDA11.8/GCC13；texture错误消失，宏冲突仍在，tool_failed |
| `polygeist-frontend-oo74lyqu/report.json` | `91f02f310cf411cc1fac77dd30a111596d2b37b77e1a2a6f205d79d3cf540b61` | CUDA11.8/GCC11；无此前头错误，vector cleanup诊断后ValueCategory::store断言，tool_failed |
| `polygeist-frontend-uq3mjvsz/report.json` | `b2ffc54d86cf8f8d0385052c121fc531edb43b6c4a883f804d849d4463852bc3` | symbol=rms_norm_f32_logical32，退出0，只有两行空module |
| `polygeist-frontend-kphrlcg7/report.json` | `c25c214f79ba2534c6964434af54ea0542b54393e4c7ab1c333386e2c5b393a0` | symbol=_Z22rms_norm_f32_logical32PKfPfif，退出0，只有两行空module |

后两份报告按记录器定义为 emitted_unverified_ir；人工检查 output.mlir 无
函数、launch 或计算体，因此均不能计作 kernel 转换成功。前两份选择 `*`。
CUDA11.8 partial-support warning 仍保留。头文件传递闭包未完整哈希。

固定源码 clang-mlir.cc 5280–5306/5360–5381 使用 mangled name 选择；
5178–5188 将 device函数设为private。没有直接追踪是哪一pass移除函数，
不能断言空module的全部原因已经确定。

## 下一步与边界

保留计算函数逐字与完整 kernel/launch 配置，建立显式 public host入口；
把文件 IO、vector和设备信息驱动放在外部harness，并记录新增人工接入修改。
这不是自动适配；不能把局部输入成功说成整个原程序支持。原完整输入的失败
仍保留。继续检查实际 IR、collective、共享内存与launch，不预设语义差异。
未执行 CUDA GPU、coarsening、数值或性能实验，G1未通过。
本轮仅证据文档修改，核对报告/包哈希与 `git diff --check`，未重跑273项CPU测试。

# PhysAg3D

**从单张图片生成高保真、可交互的三维资产。**

[项目主页](https://supra-3d.github.io/PhysAg3D/) · [English](README.md)

本项目结合 TRELLIS.2 的整物体生成、推理模型驱动的 Blender 细化，以及 MuJoCo 物理验证。仓库包含任务协议、生成工具、参考代码、单案例启动器和示例图片。

## 目录

| 路径 | 用途 |
|---|---|
| `reproduce.py` | 完整性校验、环境检查、案例准备和执行入口 |
| `method/` | Worker 提示词、工具协议、native 客户端及参考实现 |
| `config/` | 可按本机环境调整的配置模板 |
| `examples/` | 参考运行配置 |
| `inputs/` | 34 张示例图片 |
| `tests/` | 离线测试 |
| `docs/` | 配置、验证和结果说明 |
| `provenance/` | 外部 runtime 和模型的文件指纹 |
| `licenses/` | 第三方许可证 |

## 环境与配置

参考环境为 Windows 控制端和 Linux NVIDIA GPU 生成端。控制端需要 Python 3.12、Blender 5.2.1、兼容的 Codex CLI，以及可访问配置模型的个人账号。生成端需自行安装 TRELLIS.2 runtime、TRELLIS.2-4B、DINOv3、BiRefNet 及 CUDA 扩展；当前配置要求至少 28 GiB 空闲显存。

运行模型和推理参数保持配置中的值：`gpt-6-astra/high`，native 的分辨率 1024、24 steps、2048 纹理、seed 42。`requirements.observed.txt` 是观察到的依赖版本记录，尚不是经过独立机器验证的完整安装锁文件。

在仓库根目录执行：

```powershell
python -m venv .venv
$python = (Resolve-Path .venv/Scripts/python.exe).Path
& $python -m pip install -r requirements.observed.txt
Copy-Item config/runtime.windows-ssh.json config/runtime.local.json
```

编辑 `config/runtime.local.json`，填写本机 Python、Blender、Codex CLI 路径，远程 SSH 别名、runtime/模型目录和独立作业根目录。Python 路径应指向上面创建的环境。配置文件只保存路径与参数，使用自己的账号和 SSH 认证。

## 运行一个案例

```powershell
& $python reproduce.py verify
& $python reproduce.py doctor --config config/runtime.local.json
& $python reproduce.py doctor --config config/runtime.local.json --native
& $python reproduce.py prepare --image inputs/glossy_18_e53271e2.png --config config/runtime.local.json --out ../runs/example01
& $python reproduce.py plan ../runs/example01
& $python reproduce.py run ../runs/example01
```

仅 `run` 会开始生成并使用模型服务额度。结果必须放在仓库外的新目录中。启动器会检查已准备的输入和方法文件，并拒绝覆盖或自动恢复已尝试的案例。

主入口使用配置中的 ChatGPT 订阅执行方式。`method/trellis2-native-refine/scripts/run_api.py` 是单独的 API 密钥入口，使用它时应遵循其自身配置说明。

## 查看结果

以 `delivery.json` 为准查看模型、Blender 文件、物理场景、视频和预览页路径。`execution.json` 记录执行状态；进程正常退出不代表资产已经通过视觉或物理验证。

`method/assisted_reference_code/` 是方法中明确包含的案例代码参考。Worker 会根据新图片和新生成候选适配其中的通用技术，不能直接运行包含旧路径或固定几何假设的脚本来替代新建模。仓库未附带模型权重和旧生成资产，独立机器上的端到端效果仍需验证。

完整性校验覆盖清单声明的源码；本地配置、输入图片、Git 元数据和虚拟环境不属于该校验范围。

详细说明：[环境与运行](docs/REPRODUCTION.zh-CN.md)、[验证范围](docs/VALIDATION.zh-CN.md)、[结果检查](docs/RESULTS.zh-CN.md)、[第三方声明](THIRD_PARTY_NOTICES.md)。

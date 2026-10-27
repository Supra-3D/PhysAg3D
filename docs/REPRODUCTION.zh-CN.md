# 环境配置与运行

## 控制端与生成端

参考配置采用 Windows 控制端和 Linux TRELLIS.2 生成端。控制端使用 Python 3.12、Blender 5.2.1、兼容的 Codex CLI；模型配置为 `gpt-6-astra/high`。CLI 需支持启动器使用的参数，`doctor` 会进行检查。Linux 控制端模板位于 `examples/runtime.linux-local.EXPERIMENTAL.json`，其完整运行效果尚未独立验证。

生成端需准备 TRELLIS.2 runtime、TRELLIS.2-4B、DINOv3、BiRefNet、CUDA 及相应扩展。当前配置要求推理前至少 28 GiB 空闲显存。native 参数为 1024 分辨率、24 steps、2048 纹理和 seed 42。

`requirements.observed.txt` 记录观察到的控制端依赖版本。外部 runtime 和主模型的已记录文件指纹分别保存在 `provenance/remote_runtime_sha256.txt`、`provenance/remote_model_sha256.txt`。可在生成端使用 `verify_external.py --root <安装目录> --manifest <指纹文件>` 核对；该操作仅校验列出的文件。

## 配置路径

从仓库根目录复制 `config/runtime.windows-ssh.json` 为 `config/runtime.local.json`，然后填写：

| 字段 | 内容 |
|---|---|
| `python` | 控制端 Python 环境的绝对路径 |
| `blender` | Blender 可执行文件的绝对路径 |
| `codex` | 可直接执行的 CLI 路径 |
| `gpu` | 目标 GPU 编号 |
| `trellis.ssh_host` | 自己配置的 SSH 主机别名 |
| `trellis.python` | 生成端 Python 路径 |
| `trellis.runtime` | TRELLIS.2 runtime 目录 |
| `trellis.model` | 主模型权重目录 |
| `trellis.dino` / `trellis.rembg` | 辅助模型权重目录 |
| `trellis.jobs_root` | 本账号可写的独立任务目录 |

保持正常 SSH 主机校验，使用自己的账号和认证。配置内不要保存密钥。`config/`、`inputs/` 和本地虚拟环境均不参与源码完整性校验。

## 检查与执行

在已激活的 Python 环境中，从仓库根目录执行：

```text
python execute.py verify
python execute.py doctor --config config/runtime.local.json
python execute.py doctor --config config/runtime.local.json --native
python execute.py prepare --image inputs/glossy_18_e53271e2.png --config config/runtime.local.json --out ../runs/example01
python execute.py plan ../runs/example01
python execute.py run ../runs/example01
```

`verify` 检查源码；`doctor` 检查环境；`prepare` 创建输入、方法、配置和哈希记录；`plan` 显示命令。只有 `run` 启动生成。

运行目录应位于仓库外，每次使用新目录。准备后保留方法和输入文件不变；修改它们会被启动器拒绝。执行采用单次 worker turn 和显式墙钟预算，不会自动重试或恢复已执行案例。

## 查看与检查

查看运行目录中的 `progress.json`、`events.jsonl`、`stderr.log`、`execution.json` 和 `delivery.json`。结果文件以 `delivery.json` 的实际路径为准。

可用只绑定本机的静态服务查看结果页面：

```text
python -m http.server 8080 --bind 127.0.0.1 --directory ../runs/example01
```

打开 `http://127.0.0.1:8080/presentation/index.html`。页面回放已有模型动画，不代表在线执行物理求解。

请结合[验证范围](VALIDATION.zh-CN.md)和[结果清单](RESULTS.zh-CN.md)检查输出。环境检查通过或生成进程退出，均不能单独证明视觉和物理正确性。

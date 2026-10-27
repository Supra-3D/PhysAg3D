# 8769：同事复现交接说明

本包用于独立机器上的生成复现测试，尚未通过跨机器效果验证。第一次先跑通一个 case，保存全过程，再扩大测试范围。

## 发包人需要给什么

只需发送 `8769_colleague_handoff_20260928.zip`，里面已有：

| 路径 | 用途 |
|---|---|
| code/ | 完整8769 assisted协议、worker提示词、native客户端、历史代码参考、Blender/MuJoCo与页面工具、启动器 |
| config/runtime.windows-ssh.json | 同事改成自己的软件与服务器路径 |
| inputs/ | 两批原始8769实验的34张原图，没有旧生成结果 |
| inputs_manifest.json | 输入路径与SHA256 |
| pilot_inputs.json | 预登记6例；首轮环境跑通后每例重复3次 |
| START_HERE.zh-CN.md | 本说明 |
| RETURN_RESULTS.zh-CN.md | 运行后返回哪些文件 |

不用给同事当前聊天、原机器用户目录、Codex登录文件、SSH私钥、旧Blender/GLB、历史视频或额外的case专属生成脚本。**code/method/assisted_reference_code要保留**：它属于当前公开声明的方法。worker可以参考通用技术，不直接执行模板里的旧案例代码。

旧案例结果由发包人保管，同事生成结束后再对照。这里34张图对应原始8769 assisted；没有把后续8794混合版本50例当作同一协议。

## 一、同事准备的环境

首轮统一使用 **Windows 11控制端 + Linux TRELLIS.2服务端**，贴近历史部署。不是一台普通Windows笔记本独立承担全部GPU任务；同事需要自己可访问的Linux NVIDIA GPU环境。WSL或全Linux控制端暂不作为首轮标准配置。

Windows端：

- Python3.12 x64；历史为3.12.10。
- Blender5.2.1 LTS，记录实际blender.exe位置。
- 兼容Codex CLI，使用实际codex.exe路径，不填不可直接执行的.ps1包装脚本。
- 同事自己的ChatGPT登录和可访问gpt-6-astra/high的账号。本入口走subscription，不使用我们的API key，也不自动切到API计费。
- 可用OpenSSH客户端，能连接自己的Linux环境。

CLI安装按[OpenAI官方说明](https://learn.chatgpt.com/docs/codex/cli)中的Windows选项。安装后运行 `codex login`，用自己的账号登录；`codex login status` 查看认证方式。[官方认证说明](https://learn.chatgpt.com/docs/auth)。

先确认CLI兼容性和模型访问：启动器需要 --ignore-user-config、--skip-git-repo-check、--approve-for-me。当前审计机CLI是0.158.0-alpha.2.1，不代表所有公开发行版都支持这些参数。doctor会检查；缺少参数时返回版本和诊断，不删掉权限参数强行运行。没有目标模型时也先反馈；换模型属于另一项实验。

Linux端：

- NVIDIA GPU与可用CUDA；当前代码要求启动时至少28 GiB可用显存，24GB卡不满足默认门槛。不要仅为通过检查而降低阈值。
- 独立TRELLIS环境；历史Python3.10.21、PyTorch2.6.0+cu124。
- 自行部署TRELLIS.2 runtime、TRELLIS.2-4B、对应DINOv3和BiRefNet权重。
- 安装该runtime要求的CUDA扩展，包括o_voxel、cumesh等。
- 本账号可写的独立jobs目录，例如/srv/native-refine/jobs。

[TRELLIS.2官方部署说明](https://github.com/microsoft/TRELLIS.2)是安装起点。最新代码不自动等于历史环境。主模型/native runtime历史哈希在code/provenance/remote_*_sha256.txt。完整DINO/BiRefNet权重锁和第三方扩展构建锁尚未补齐，这是未验证条件。发现偏差要记录反馈，不能静默更换后声称环境一致。

可将code/verify_external.py与哈希清单拷到Linux执行：

```bash
python verify_external.py --root /opt/TRELLIS.2 --manifest remote_runtime_sha256.txt
python verify_external.py --root /srv/models/TRELLIS.2-4B --manifest remote_model_sha256.txt
```

它只比较清单里的文件，不证明CUDA或生成质量通过。

## 二、解压与Python环境

以下在Windows PowerShell执行。假定解压后目录为C:/repro/8769_colleague_handoff_20260928；不同位置请改第一行。

```powershell
Set-Location 'C:/repro/8769_colleague_handoff_20260928'
py -3.12 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r ./code/requirements.observed.txt
& ./.venv/Scripts/python.exe ./code/reproduce.py verify
```

依赖清单是本机观察版本，尚非外部机器重装验证过的完整锁文件。安装失败时保存错误，不自行降级后仍称同环境复现。

**不要修改code/，也不要把venv、runtime配置、日志或生成目录放进code/。** 它做完整性校验。可编辑配置在旁边的config/。本文所有命令都从解压根目录执行。

## 三、配置自己的路径

编辑config/runtime.windows-ssh.json。Windows路径建议使用/，避免JSON反斜线转义。

| 字段 | 填什么 |
|---|---|
| python | 新venv完整路径，如C:/repro/8769_colleague_handoff_20260928/.venv/Scripts/python.exe |
| blender | 自己的blender.exe完整路径 |
| codex | 自己可执行的Codex CLI完整路径 |
| gpu | Linux目标卡编号，如0 |
| trellis.ssh_host | 自己配置的SSH别名，如trellis-repro |
| trellis.python | Linux TRELLIS环境中的Python |
| trellis.runtime | Linux TRELLIS.2源码根目录 |
| trellis.model | 含pipeline.json、texturing_pipeline.json、ckpts的主模型目录 |
| trellis.dino / trellis.rembg | 对应本地DINOv3 / BiRefNet权重目录 |
| trellis.jobs_root | Linux上自己可写的独立任务根目录 |

保留gpt-6-astra/high以及native的1024/24/2048/42。单例默认墙钟预算10800秒；新适配器不自动复刻历史批处理的容量排队/续跑策略。

SSH需要能无交互连接：配置自己的认证，正常核验服务器主机指纹，不关闭主机校验、不使用发包人私钥。先手工验证 `ssh trellis-repro`。ssh_host是SSH主机别名，不是网页网址。

## 四、先检查再生成

```powershell
& ./.venv/Scripts/python.exe ./code/reproduce.py doctor --config ./config/runtime.windows-ssh.json
& ./.venv/Scripts/python.exe ./code/reproduce.py doctor --config ./config/runtime.windows-ssh.json --native
```

这两条不调用生成模型。第一条检查本地程序/依赖；第二条检查Linux路径/imports/native环境。全部通过后继续。doctor通过仍不等于账号模型可用或资产质量通过。

第一例使用预登记pilot清单第一项，不是按旧结果质量挑选：

```powershell
& ./.venv/Scripts/python.exe ./code/reproduce.py prepare --image ./inputs/8769_Appearance20/glossy_18_e53271e2.png --config ./config/runtime.windows-ssh.json --out C:/repro/runs/glossy18_repeat01
& ./.venv/Scripts/python.exe ./code/reproduce.py plan C:/repro/runs/glossy18_repeat01
& ./.venv/Scripts/python.exe ./code/reproduce.py run C:/repro/runs/glossy18_repeat01
```

prepare只复制方法、该张原图、结构化配置并记录哈希/新作业根；plan只展示命令。**run才开始推理，使用同事自己的额度。** 不需要另开聊天逐步指导建模，也不要追加本例分割或关节建议。

终端可能长时间不打印模型进度；本例events.jsonl、stderr.log、progress.json包含进度/错误。可在另一个PowerShell查看：

```powershell
Get-Content C:/repro/runs/glossy18_repeat01/events.jsonl -Tail 20 -Wait
```

不要重复运行同一目录。本适配器拒绝自动恢复/重试；失败先保存记录，复试改用glossy18_repeat02等新目录。输入观察、脚手架、新native、Blender细化、物理及可见运动检查由本例worker按完整协议执行；这不是generation-only入口。

## 五、结果与检查

先看execution.json、delivery.json。executor_completed仅表示推理进程结束，不等于资产通过。再检查delivery列出的文件。常见路径：asset/refined.blend、asset/refined.glb、physics/scene.xml、media/motion.mp4、presentation/index.html；实际以delivery为准。

生成结束后，同事可在自己的终端启动只绑定本机的静态服务：

```powershell
& ./.venv/Scripts/python.exe -m http.server 8080 --bind 127.0.0.1 --directory C:/repro/runs/glossy18_repeat01
```

打开 http://127.0.0.1:8080/presentation/index.html 。这是查看自己新生成结果，不是接入旧站点。若端口占用则自行选空闲端口。

检查每个关节静止、中间、端点的可见表面运动，有无飞散、断开、错误枢轴和穿透；柔性、近似动作与静态转台分别记录。物理失败但有动画只能算候选/部分结果。保留失败尝试，完整反馈清单见RETURN_RESULTS.zh-CN.md。

## 六、如何回答是否依赖原机器聊天

包里没有发包人的聊天历史、账号、旧产物或案例反馈。同事用自己的干净系统与账号，从新native开始生成，再交回结果事后对照，才是需要的证据。新目录、禁用memory、seed42本身都不构成严格隔离或质量复现证明。

先跑这一例确认环境，再做pilot_inputs.json中的6例各3次；随后扩展到全部34例。保留所有失败和人工干预，不只挑最好的一次。比较外观、部件归属、运动和真实物理记录，不要求随机生成的GLB逐字节相同。

方法仍标为8769-assisted-release-candidate.0，历史参考代码明确属于方法。新启动层尚未做独立机器端到端效果测试。反馈应区分环境跑不通、生成完成但交互错误、物理失败、完整检查通过。

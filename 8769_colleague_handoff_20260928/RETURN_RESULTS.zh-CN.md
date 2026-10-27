# 请同事返回的结果

每例返回完整新运行目录：input、method、runtime、identity、prompt、execution、events/stderr、progress、delivery、生成脚本、native回执和候选、Blender/GLB、physics场景与依赖/轨迹/报告、渲染、页面和视频。若太大，至少先回identity.json、execution.json、delivery.json、progress.json、完整错误日志和静止/中间/端点截图或视频；大文件保留，不删除失败尝试。

附OS、Python、Blender、CLI、CUDA/PyTorch版本，模型/effort，native源码与权重核对结果，doctor输出。预检失败时不用继续生成，先回预检日志和版本。

每例填写run编号、输入SHA256、是否全新native、是否有人给个案指导/手动修复、native成功、细化成功、可见部件动作、柔性状态、物理状态、限制、失败阶段和耗时。进程退出不等于交互或物理通过。

不要打包个人.codex、auth.json、SSH私钥、.env、登录缓存或服务密钥。日志分享前检查是否意外包含机密。新结果仅用于事后比较，不回灌到尚未执行的新case提示词。

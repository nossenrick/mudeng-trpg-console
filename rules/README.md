# 规则文档

规则助手使用本地文档检索，不把整份规则书或当前战役状态发送给模型。

- `coc7e-keeper.pdf` / `.txt`：本地导入的《克苏鲁的呼唤》第七版守秘人规则书中文完整版。
- `dnd5e-srd.pdf` / `.txt`：Wizards of the Coast 发布的 D&D 5e SRD 5.1。
  https://media.wizards.com/2023/downloads/dnd/SRD_CC_v5.1.pdf

CoC 文档包含完整规则书正文；助手会排除明显涉及模组剧情示例的片段，并且不会把当前战役状态发送给模型。

更新 PDF 后，可运行：

```powershell
.\.venv\Scripts\python.exe extract_rules.py
```

重新生成对应的 `.txt` 检索文本。

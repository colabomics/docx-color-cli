# docx-color-cli

[![PyPI](https://img.shields.io/pypi/v/docx-color-cli?label=pypi)](https://pypi.org/project/docx-color-cli/)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
[![CI](https://github.com/colabomics/docx-color-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/colabomics/docx-color-cli/actions)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

[English](README.md) | 简体中文

---

### 论文改完了，还得手动标红？😩

回复审稿人已经够头疼了。好不容易改完论文，结果还要把新增的每句话、每个公式找出来，一个个改成红色……

**这种重复劳动，交给电脑吧！**

`docx-color-cli` 可以根据 Word 的修订记录，自动找出论文中新增的内容，并在最终文档中标红。

**一行命令，搞定论文标红！🔴**

## ✨ 为什么需要它？

想象一下：

你花了几个星期回复审稿意见，终于修改完论文。

Reviewer #2 又让你增加了一堆实验、分析和数学公式。

你以为终于可以提交了，结果编辑要求：

**“Please highlight all changes in the revised manuscript.”**

于是，你又开始在 Word 里一段一段找修改内容……

😵‍💫

现在，可以把这件事交给 `docx-color-cli`。

- 🔴 **新增内容自动标红** — 不用再逐段查找、手动改颜色。
- 📄 **尽量保持原样** — 正文、公式、表格、参考文献，该保留的都保留。
- ⚡ **一行命令搞定** — 不需要复杂的操作。
- 🔓 **免费、开源、本地运行** — 论文不用上传到任何服务器。

**把时间留给科研，而不是 Word 格式调整。**

## 🎬 看看效果

![docx-color-cli 使用演示](assets/demo.gif)

**两个 Word 文件，一行命令，新增内容自动标红！🔴**

准备好带修订记录的 `change_tracked.docx` 和接受全部修订后的 `change_accepted.docx`，然后运行：

```bash
docx-color \
  examples/change_tracked.docx \
  examples/change_accepted.docx \
  examples/change_colored.docx
```

**🎉 搞定！**

程序会自动识别新增内容，并将能够可靠定位的文字标记为红色。没修改的内容保持原样，数学公式、表格和参考文献也尽量保留原有格式。

**想亲自试试？** 这两个示例文件已经放在 [`examples/`](examples/) 目录里，直接运行上面的命令即可！

## 🚀 三步搞定

### 第一步：安装

需要 Python 3.11 或更新版本。

目前新版还没有正式发布，可以先从最新开发代码安装：

```bash
python -m pip install .
```

如果你使用 [uv](https://docs.astral.sh/uv/)，也可以：

```bash
uv tool install .
```

等新版正式发布后，安装会更简单：

```bash
uv tool install docx-color-cli
```

### 第二步：准备两个 Word 文件

你只需要准备同一份论文的两个版本。

**📄 `tracked.docx` — 带修订记录的论文**

就是你使用 Word 的「修订」（Track Changes）功能修改过的文档。

**📄 `accepted.docx` — 接受全部修订后的论文**

准备起来也很简单：

1. 用 Word 打开 `tracked.docx`。
2. 另存一个副本，保留原始文件。
3. 点击 **审阅 → 接受 → 接受所有修订**。
4. 关闭「修订」，保存为 `accepted.docx`。

注意：两个文件必须对应同一次修改。生成接受修订的副本后，不要再单独修改其中的内容。

**小提醒：** `docx-color-cli` 不会替你接受修订。这一步需要先在 Word 中完成。

### 第三步：运行！

打开终端，输入：

```bash
docx-color tracked.docx accepted.docx colored.docx
```

**🎉 搞定！**

你会得到一个新的文件：

`colored.docx`

能够可靠识别的新增内容已经自动标红。

原来的两个 Word 文件不会被修改。

整个流程就是：

**📝 带修订的论文 + ✅ 接受修订的论文 → 🔴 新增内容标红的论文**

## 🎨 不喜欢红色？换一个！

默认颜色是红色。

如果期刊要求用蓝色标记修改内容，只需要加一个参数：

```bash
docx-color tracked.docx accepted.docx colored.docx --color 0000FF
```

想换其他颜色也可以，使用六位十六进制颜色代码即可，不需要加 `#`。

## 📋 它会对论文做什么？

| 文档内容 | 处理结果 |
|---|---|
| ✏️ 新增文字 | 自动标红 |
| 📄 原有文字 | 保持原来的颜色和格式 |
| 🗑️ 删除的文字 | 已在接受修订时移除 |
| ∑ 数学公式 | 支持的新增公式也可以标红 |
| 📊 表格和图片 | 保留原有内容和结构 |
| 📚 参考文献 | 保留引用字段和链接 |

这里最重要的是：

**工具不会重新生成你的论文，而是在接受修订后的原始文档上修改字体颜色。**

这意味着公式仍然是可编辑的 Word 公式，参考文献也不会被转换成普通文本。

对于无法可靠识别的新增内容，程序会保留原样，而不是随便猜测。

## 📊 怎么知道有没有漏标？

运行结束后，终端会告诉你处理结果。

你可能看到以下三种状态：

**✅ SUCCESS — 处理成功**

文档已经生成并通过检查，没有报告尚未解决的着色候选内容。

**🟡 PARTIAL — 部分完成**

文档已经生成，但有些复杂修改无法可靠标红，或者附加报告保存遇到了问题。

别担心，程序会告诉你发生了什么。建议打开 Word 检查一下。

**❌ FAILED — 处理失败**

没有生成新的输出文档。如果目标位置原本就有文件，程序会尽量保留它。

想保存更详细的结果？加上 `--report`：

```bash
docx-color tracked.docx accepted.docx colored.docx --report result.json
```

报告主要记录处理数量和检查状态，不会写入你的论文正文。

如果想查看所有命令选项：

```bash
docx-color --help
```

查看当前版本：

```bash
docx-color --version
```

> 💡 **给自动化脚本使用的小提示：** 退出码 `0` 代表已经生成并验证 DOCX，但结果仍可能是 PARTIAL。需要确认完整着色时，请检查 JSON 报告中的 `overall_status` 和 `coloring_status`。

## ❓ 你可能还想问……

### Word 公式也能标红吗？

**可以！**

对于 Word 原生公式，工具支持多种常见的新增内容，包括变量、分数、求和符号等。

而且，公式依然可以在 Word 中编辑。

当然，特别复杂的公式内部修改可能暂时无法自动处理。

### Zotero 引用会不会坏掉？

工具会以接受修订后的 Word 文档为基础，保留其中的引用字段、超链接以及其他文档结构。

它不会重新生成参考文献，也不会主动将 Zotero 字段转换成普通文字。

不过，如果引用区域涉及复杂修订，有些新增文字可能无法自动标红。

**建议提交论文前，顺手检查一下重要引用。**

### 会把我的 Word 格式弄乱吗？

工具的设计原则是：

**只改新增内容的颜色，其他内容尽量不碰。**

程序会检查生成文档的内容和结构是否与接受修订后的文档保持一致。

但 Word 的功能非常丰富，不能保证所有复杂文档都能完美处理。

所以，正式投稿前还是建议打开输出文件看一眼。

### 我的原始论文安全吗？

**原始文件不会被修改。**

`tracked.docx` 和 `accepted.docx` 都是输入文件。

程序会另行生成 `colored.docx`。

如果你反复运行相同命令，成功转换会替换已有的 `colored.docx`，因此建议不要把唯一的重要文件作为输出。

### 论文会上传到哪里吗？

**哪里都不会！**

整个处理过程都在你的电脑上完成，不需要把论文上传到外部服务器。

对于尚未发表的论文，这一点尤其重要。

### 如果有些新增内容没有标红怎么办？

Word 修订记录有时比想象中复杂。

例如，同一段话被多次修改、文字被移动、数学公式内部结构变化，或者两个版本无法准确对应。

遇到这些情况，工具会优先保证文档安全。

**能确定的就标红，不能确定的就保留原样，并报告未完成的部分。**

与其把没修改过的内容错误标红，不如留给你最后确认。

## ⚠️ 使用前的小提醒

虽然工具可以省去很多重复劳动，但还有几个地方值得注意：

- 两个输入必须来自同一份 Word 文档。
- 记得先在 Word 中接受全部修订，生成 `accepted.docx`。
- 某些复杂修订、字段变化和特殊数学结构可能暂不支持。
- 当前不支持 Strict OOXML 格式。
- 特别大或异常压缩的 DOCX 文件可能因为安全限制被拒绝。
- 运行时不要同时编辑输入和输出文件，最好先关闭 Word 中打开的目标文件。
- 输出文件和 JSON 报告请使用明显不同的文件名，不要只靠大小写区分。
- **投稿之前，记得检查一下最终文档。**

目前工具已在 macOS 上使用 Python 3.11、3.12 和 3.13 完成本地测试。Linux 和 Windows 的跨平台验证仍在进行中。

## 🐍 还可以在 Python 中使用

如果你想在自己的 Python 脚本里批量处理论文，也可以直接调用：

```python
from docx_color_cli import color_revisions

result = color_revisions(
    "tracked.docx",
    "accepted.docx",
    "colored.docx",
    color="FF0000",
)

print(result["overall_status"])
```

程序也会提供相应的错误信息，方便你在脚本中判断是否处理成功。

如果你以前用过旧版，需要注意：新版改成了三个文件路径，旧的一文件或两文件工作流程以及 `--unchanged-color`、`--reference`、`--check` 等参数已不再支持。

Python 用户请改用 `color_revisions()`。

## ❤️ 欢迎一起改进！

如果这个工具帮你省下了几个小时的 Word 操作时间，那它就已经完成任务了。😄

发现 Bug？遇到某种无法正确标红的修订？

欢迎 [提交 Issue](https://github.com/colabomics/docx-color-cli/issues) 或 Pull Request。

如果要分享有问题的文档，请尽量使用**不包含私人论文内容的最小示例**。

觉得有用的话，也欢迎给项目点个 ⭐！

## 📄 License

本项目采用 [MIT License](LICENSE) 开源。
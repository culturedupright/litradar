# 参与开发

## 分支与提交

- `main` 始终可运行，不直接堆半成品。
- 功能分支：`feat/card-extraction`、`fix/pmc-figure-url`。
- 提交前缀：`feat:`、`fix:`、`docs:`、`test:`、`chore:`、`refactor:`。
- 一次提交只做一件事，提交信息写“为什么”，不是“改了什么”。

## 本地检查

```bash
pip install -e ".[dev]"
pytest
python -m compileall src
```

## 新增能力的顺序

1. 先写离线单测（不联网、不调模型）；
2. 再写实现，让单测过；
3. 涉及网络的，加一个可跳过的集成测试，用环境变量开关；
4. 更新 `CHANGELOG.md` 的 `Unreleased`。

## 数据与隐私

- 不提交 `data/`、`runs/`、`*.db`、`.env`。
- 不把 API Key、手机号、未发表数据写进代码或测试。
- 测试用固定的小样本，不拉全量文献。

## 发版

```bash
# 确认 main 干净、CI 绿
git tag -a v0.1.0 -m "v0.1.0: 检索层"
git push origin v0.1.0
```

推 tag 后 GitHub Actions 自动构建 sdist/wheel 并创建 Release。

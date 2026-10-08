# 团队余额看板

公开页面展示智星云主账号下各 API Key 的名称、人民币剩余额度、总额度、已用金额和状态。Cloudflare Worker 每 10 分钟触发一次 GitHub Actions；Actions 生成 `usage.json` 并部署到 GitHub Pages。GitHub Pages 只托管静态文件，无需常驻服务器。

## 首次部署

1. 在仓库 **Settings → Pages** 中，将 **Build and deployment → Source** 设为 **GitHub Actions**。
2. 在 **Settings → Secrets and variables → Actions → Repository secrets** 中添加：

   | 名称 | 内容 |
   | --- | --- |
   | `GALAXY_PHONE` | 智星云主账号手机号 |
   | `GALAXY_PASSWORD_MD5` | 智星云网页登录所用的密码 MD5 摘要 |

   现有仓库已配置这两个 Secrets，迁移到 Cloudflare 定时器时无需重新填写。若日后重建仓库，请通过私有渠道设置；不要把值提交到仓库或发到聊天、工单。摘要可直接用于网站登录，必须与密码一样保密。

3. 在仓库 **Actions → Publish balance panel → Run workflow** 手动运行一次。确认两个作业 `build`、`deploy` 成功，打开 Pages 链接，核对成员数量、金额及更新时间。GitHub 托管的运行环境必须能够正常登录智星云；如出现验证码，需要先人工处理。
4. 创建只授权 `AcerMo/Team-Balance-Panel`、具有 **Actions: Read and write** 权限的 GitHub 细粒度个人访问令牌。在 Cloudflare Workers Free 账号中部署 `scheduler/`，将令牌存为 Worker 的加密密钥 `GITHUB_ACTIONS_TOKEN`。不要把令牌填入 Worker 的普通变量或提交到仓库。
5. `scheduler/wrangler.toml` 使用 UTC 的 `*/10 * * * *`，即北京时间每小时的 00、10、20、30、40、50 分触发。Cloudflare 的首次 Cron 配置可能需要最多 15 分钟生效。GitHub 工作流只接受 `workflow_dispatch`，以避免重复登录。

拥有 Cloudflare Workers 编辑权限的账号可在任意电脑维护定时器：首次使用 Cloudflare Workers 时，先打开 Workers & Pages 页面初始化账号的 `workers.dev` 子域；然后在 `scheduler/` 目录运行 `npx wrangler@4.148.0 deploy` 部署代码，再运行 `npx wrangler@4.148.0 secret put GITHUB_ACTIONS_TOKEN`，按无回显提示输入上述 GitHub 令牌。令牌过期时只需重新设置该密钥；不需要重建网页或智星云 Secrets。不要为此升级到 Workers Paid。

## 失败与恢复

一次同步失败时不会部署新页面。GitHub Pages 保留上一次成功发布的余额，网页会提示数据更新延迟。工作流只记录错误类别，不记录手机号、密码摘要、会话、完整 API Key 或接口响应。

如果网站要求验证码、密码被拒绝或新登录无法使用，工作流会自动暂停，以免每 10 分钟重复登录。处理问题并更新 Secrets 后，在 **Actions** 页面重新启用工作流，先手动运行确认成功，再恢复定时任务。GitHub Actions 的失败通知可用于发现问题。

Cloudflare 触发器只发送工作流启动请求，不读取智星云凭据或公开数据。若 Worker 密钥失效，更新 `GITHUB_ACTIONS_TOKEN` 并检查 Cloudflare 的 Cron 运行记录。仓库若改为私有，Pages 和 Actions 的可用范围与额度取决于 GitHub 套餐。

## 安全与数据范围

- 当前仓库的 `.github/workflows/publish.yml` 在 Actions 任务中读取仓库 Secrets。它调用智星云的登录接口，以及额度配置和 Key 列表两个查询接口。不会调用创建、编辑、删除或充值接口。
- 完整 API Key、网站会话和登录凭据只存在于运行任务的内存中。`site/usage.json` 仅包含允许公开的名称、额度、状态和更新时间，且被 `.gitignore` 排除在 Git 历史外。公开网页可被任何拿到链接的人查看。
- 人民币金额使用智星云返回的汇率配置进行换算；总额度按剩余额度加累计已用量计算。原站内部接口或登录规则改变时，需要更新同步代码。
- 当前设计每次任务新登录一次。若网站限制该频率，降低 Worker 运行频率。

## 本地验证

无需安装第三方 Python 依赖：

```bash
python -m unittest discover -s tests -v
node --check site/app.js
node --test scheduler/worker.test.mjs
```

本地测试使用模拟接口，不需要真实登录信息。`python sync.py` 只应在已安全设置 `GALAXY_PHONE` 和 `GALAXY_PASSWORD_MD5` 的环境中执行；成功时生成被忽略的 `site/usage.json`。

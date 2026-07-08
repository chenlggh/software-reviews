# 📋 项目级 GitHub Actions 配置（Cloudflare Pages 原生部署方案）

# 方案 A：通过 Actions 部署（推荐——上面已经配置）
# GitHub Actions → Wrangler → Cloudflare Pages
# 优点：可以串 Python 生成脚本、Hugo 构建
#
# 参考上面的 .github/workflows/hugo-deploy.yml

# 方案 B：Cloudflare Pages 原生连接 GitHub（简单方案）
# 如果你不想用 Actions，可以直接在 Cloudflare Pages Dashboard 里连接这个 GitHub 仓库：
#
# Cloudflare Dashboard → Pages → Create a Project → Connect to Git
# Build command: hugo --minify
# Build output: public
# Environment variables: HUGO_VERSION = 0.136.0
# 注意勾选 "Include submodules" 来拉取 PaperMod 主题

# 两种方案选其一即可。

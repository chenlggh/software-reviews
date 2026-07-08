# Software Reviews SEO Site 🚀

程序化 SEO 静态站点——软件评测与对比网站

基于 **Hugo** + **PaperMod** 主题，通过数据模板批量生成 SEO 页面，部署在 **Cloudflare Pages** 上。

## 技术栈

| 组件 | 用途 |
|------|------|
| Hugo | 静态站点生成器 |
| PaperMod | Hugo 主题（Git 子模块） |
| Python | 批量页面生成脚本 |
| GitHub Actions | CI/CD 自动构建 |
| Cloudflare Pages | CDN 部署托管 |

## 项目结构

```
D:\Frontend\
├── archetypes/              # Hugo 内容模板
│   ├── list-page.md         # "Best X for Y" 类型
│   ├── comparison.md        # "A vs B" 类型
│   └── guide.md             # "How to Choose" 类型
├── assets/
│   └── css/main.css         # 全局样式
├── config/_default/         # Hugo 配置
│   ├── params.toml          # 站点参数（AdSense、SEO 等）
│   └── menus.toml           # 导航菜单
├── content/                 # 内容目录
│   ├── posts/               # 博客文章 / 评测页面
│   ├── about/               # 关于页面
│   ├── privacy/             # 隐私政策
│   └── terms/               # 使用条款
├── data/                    # 结构化数据
│   ├── software.yaml        # 软件数据库（完整配置）
│   └── software.csv         # 生成组合数据（给 Python 用）
├── layouts/                 # 自定义布局
│   ├── _default/            # 基础模板
│   ├── partials/            # 可复用组件
│   ├── shortcodes/          # 短代码（表格、按钮）
│   └── index.html           # 首页模板
├── scripts/                 # Python 工具脚本
│   ├── generate_pages.py    # 批量页面生成器
│   ├── page_list.py         # 页面组合清单生成器
│   └── requirements.txt     # Python 依赖
├── static/                  # 静态资源
│   ├── robots.txt           # SEO
│   ├── ads.txt              # AdSense
│   ├── _headers             # Cloudflare 安全头
│   └── _redirects           # URL 重定向
├── themes/PaperMod/         # PaperMod 主题（git submodule）
├── hugo.toml                # Hugo 主配置
└── .github/workflows/       # CI/CD
```

## 本地运行

### 前提条件

- [Hugo Extended](https://gohugo.io/installation/) v0.136.0+
- Python 3.10+
- Git

### 初始化

```bash
# 克隆仓库（包含子模块）
git clone --recursive <repo-url>
cd <repo-dir>

# 或者如果已克隆
git submodule update --init --recursive
```

### 生成页面

```bash
# 从 YAML+CSV 数据自动生成页面
python scripts/generate_pages.py

# 查看可生成的页面组合
python scripts/page_list.py

# 生成组合 CSV
python scripts/page_list.py --csv
```

### 启动开发服务器

```bash
hugo server -D
```

访问 http://localhost:1313/

### 构建生产版本

```bash
hugo --minify
```

输出在 `public/` 目录。

## 数据驱动流程

```
data/software.yaml (软件数据库)
        │
        ▼
scripts/generate_pages.py (模板 + 数据 → Markdown)
        │
        ▼
content/posts/*.md (Hugo 内容文件)
        │
        ▼
hugo build (生成静态 HTML)
        │
        ▼
public/ (部署到 Cloudflare Pages)
```

## 部署到 Cloudflare Pages

### 方案 A：GitHub Actions（推荐）

1. 把仓库推送到 GitHub
2. 在 GitHub → Settings → Secrets 添加：
   - `CF_API_TOKEN` — Cloudflare API Token (权限: Pages:Write)
   - `CF_ACCOUNT_ID` — Cloudflare 账户 ID
3. 推送 `main` 分支自动部署

### 方案 B：Cloudflare Pages 直接连接

1. Cloudflare Dashboard → Pages → Create a Project → Connect to Git
2. 选择这个仓库
3. 构建设置：
   - **Framework preset**: Hugo
   - **Build command**: `hugo --minify`
   - **Build output directory**: `public`
   - **Environment variables**:
     - `HUGO_VERSION = 0.136.0`
4. 勾选 **Include submodules**
5. 点击 **Save and Deploy**

## Google AdSense 接入

1. 在 `config/_default/params.toml` 中设置：
   ```toml
   [adsense]
     enabled = true
     publisher_id = "ca-pub-XXXXXXXXXXXXXXXX"
   ```
2. 更新 `static/ads.txt` 填入你的 AdSense publisher ID
3. 在 `.env` 或 Cloudflare Pages 环境变量中设置 `HUGO_ENV=production`

## 内容策略

### 页面类型

| 类型 | 模板 | 生成方式 |
|------|------|---------|
| 列表页 | `archetypes/list-page.md` | Python 批量生成 |
| 对比页 | `archetypes/comparison.md` | 手动精写 |
| 指南页 | `archetypes/guide.md` | 手动精写 |

### 三阶段计划

| 阶段 | 时间 | 目标 |
|------|------|------|
| 手动启动 | 0-3 月 | 30-60 篇核心内容 |
| 半自动化 | 3-6 月 | 扩展到 300-500 页 |
| 规模化 | 6-12 月 | 1000+ 页面，多语言扩展 |

## 关键脚本说明

### `scripts/generate_pages.py`

读取 `data/software.csv` 和 `data/software.yaml`，生成 "Best X for Y" 格式的 Hugo Markdown 页面。

```bash
python scripts/generate_pages.py

# 可选参数
python scripts/generate_pages.py \
  --csv data/software.csv \
  --yaml data/software.yaml \
  --output content/posts \
  --year 2026 \
  --limit 5   # 只生成 5 个页面测试
```

### `scripts/page_list.py`

列出所有可能的页面组合，方便规划内容策略。

```bash
python scripts/page_list.py              # 打印组合清单
python scripts/page_list.py --csv        # 输出 CSV 文件
python scripts/page_list.py --types list comparison   # 只生成指定类型
```

## SEO 特性

- ✅ JSON-LD 结构化数据 (Article, BreadcrumbList, Product)
- ✅ 自动 Sitemap.xml 生成
- ✅ 语义化 HTML 结构
- ✅ Open Graph / Twitter Cards
- ✅ Canonical URL
- ✅ 面包屑导航
- ✅ 内部链接网络
- ✅ 响应式设计 (移动端优先)
- ✅ 缓存策略 (_headers)
- ✅ 最小化 HTML/CSS

## 许可证

MIT

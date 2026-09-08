# NBA球员数据分析与薪资预测平台 Pro版

> 本科毕设全面升级迭代版本 | 作者：黄起 21760203 | 上海体育大学数据科学与大数据技术专业

## ✨ 版本亮点

相比原始毕设版本的全面升级：

| 维度 | 原始版 | Pro版 |
|------|--------|-------|
| UI设计 | 基础蓝色按钮 | 现代化深色主题数据平台风格 |
| 预测模型 | 5项特征 + XGBoost | **49项特征** + 调优XGBoost + 置信区间 |
| 数据浏览 | 静态表格 | 搜索/筛选/排序/分页 + 球员详情弹窗 |
| 可视化 | 2张matplotlib图 | **8种交互式ECharts图表** |
| AI助手 | 百度AppBuilder | **DeepSeek大模型** + 球员数据上下文注入 |
| 论坛 | 基础发帖 | 发帖/评论/点赞/浏览量/分页 |
| 球员对比 | 无 | **双球员雷达图+13项数据对比** |
| 篮球资讯 | 无 | **虎扑新闻爬取+一键获取+100条缓存** |
| 篮球教学 | 无 | **8大分类+8篇系统教程+B站视频内嵌** |
| 全局搜索 | 无 | **球员+新闻+教学统一搜索** |
| 球员中文名 | 英文 | **300+球员中文译名显示** |
| 响应式 | 无 | 完整移动端适配 |
| 架构 | 单文件500行 | 模块化前后端分离设计 |

## 🏗️ 技术栈

- **后端**：Flask + Flask-SQLAlchemy + Flask-Login
- **数据库**：SQLite
- **机器学习**：XGBoost（49项特征，300棵树，5层深度）
- **前端可视化**：Apache ECharts 5.4
- **AI大模型**：DeepSeek Chat（deepseek-chat）
- **样式**：自定义CSS变量主题系统

## 📁 项目结构

```
NBA数据分析平台_Pro版/
├── app.py                      # 后端主程序
├── player_names.py             # 球员中文译名表
├── teaching_data.py            # 篮球教学数据
├── requirements.txt            # Python依赖
├── render.yaml                 # Render部署配置
├── Procfile                    # 启动配置
├── README.md                   # 本文件
├── static/
│   ├── css/style.css           # 全局样式
│   ├── js/main.js              # 通用JS工具
│   ├── js/echarts.min.js       # ECharts库
│   └── data/                   # NBA数据集
└── templates/
    ├── base.html               # 基础布局
    ├── index.html              # 首页仪表盘
    ├── players.html            # 球员数据浏览
    ├── compare.html            # 球员对比
    ├── prediction.html         # 薪资预测
    ├── visualization.html      # 数据可视化
    ├── ai_chat.html            # AI智能助手
    ├── forum.html              # 论坛列表
    ├── forum_post.html         # 帖子详情
    ├── news.html               # 篮球资讯
    ├── teaching.html           # 篮球教学
    ├── teaching_detail.html    # 教学详情
    ├── search.html             # 搜索结果
    ├── login.html              # 登录
    ├── register.html           # 注册
    └── upload.html             # 数据上传
```

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key

# 3. 运行应用
python app.py

# 4. 浏览器访问
# http://127.0.0.1:5000
```

**默认管理员账号**：admin / admin123（首次启动自动创建）

## ⚙️ 环境变量配置

复制 `.env.example` 为 `.env` 并填入你的配置：

```bash
# DeepSeek API（AI聊天功能必需）
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL=deepseek-chat

# Flask配置
FLASK_ENV=production
SECRET_KEY=your-secret-key
```

## 🚀 部署到 Render（推荐）

### 方式一：一键部署（使用 render.yaml）

1. 将代码推送到 GitHub 仓库
2. 登录 [Render.com](https://render.com)
3. 点击 **New +** → **Web Service**
4. 连接你的 GitHub 仓库
5. Render 会自动识别 `render.yaml` 配置
6. 在环境变量中填入 `DEEPSEEK_API_KEY`
7. 点击部署，等待构建完成

### 方式二：手动配置

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 120`
- **环境变量**:
  - `DEEPSEEK_API_KEY`（必填）
  - `DEEPSEEK_API_URL`（可选，默认 https://api.deepseek.com/chat/completions）
  - `DEEPSEEK_MODEL`（可选，默认 deepseek-chat）

> **注意**：Render 免费版使用 SQLite 数据库，应用重启后论坛数据会丢失。如需持久化，建议配置 PostgreSQL。

## 📊 核心功能

### 1. 数据仪表盘
- 6项关键指标卡片
- 薪资分布直方图、得分-薪资散点图
- 球队薪资总额柱状图、年龄-薪资趋势图
- 薪资Top10、得分Top10排行榜

### 2. 球员数据浏览
- 467名球员完整数据
- 姓名搜索（支持中英文）、位置/球队筛选
- 17项指标点击排序
- 分页浏览
- 点击球员查看详情弹窗

### 3. 球员对比
- 搜索选择两名球员
- 6维能力雷达图
- 13项详细数据对比，自动高亮优势方

### 4. 薪资预测模型
- 49项特征输入
- XGBoost回归算法
- 预测结果 + 置信区间
- 特征重要性可视化

### 5. 数据可视化（8种图表）
- 薪资分布、位置薪资对比、得分vs薪资、PERvs薪资
- 球队薪资总额、年龄薪资趋势、位置能力雷达图、特征重要性

### 6. AI智能助手（DeepSeek）
- DeepSeek大模型驱动的篮球问答
- 自动识别问题中的球员名并注入数据上下文
- 多轮对话历史记忆

### 7. 篮球资讯
- 虎扑NBA新闻爬取
- 一键获取今日新闻
- 100条新闻缓存

### 8. 篮球教学
- 8大分类：基础技术、投篮、运球、传球、防守、体能、战术、规则
- 8篇系统教程
- B站视频内嵌播放

### 9. 篮球论坛
- 发帖、评论、点赞、浏览量统计

### 10. 全局搜索
- 球员、新闻、教学统一搜索

## 🔧 API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/players` | GET | 球员列表 |
| `/api/player/<name>` | GET | 球员详情 |
| `/api/predict` | POST | 薪资预测 |
| `/api/chart/<type>` | GET | 图表数据 |
| `/api/ai-chat` | POST | AI对话 |
| `/api/news/refresh` | POST | 刷新新闻 |

## 📝 开发说明

- 数据集：2022-23赛季NBA球员数据（467名球员，52项统计）
- 薪资单位：美元
- 所有图表支持响应式自适应
- 深色主题，护眼专业风格

---

**上海体育大学 数据科学与大数据技术专业**
**学号：21760203  姓名：黄起**

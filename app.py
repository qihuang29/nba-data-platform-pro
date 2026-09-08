"""
NBA球员数据分析与薪资预测平台 Pro版
作者：黄起 21760203
技术栈：Flask + XGBoost + ECharts + DeepSeek AI
"""

import os
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime
from io import BytesIO
import base64

# 加载环境变量（本地开发用，生产环境由平台注入）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session, flash)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         login_required, logout_user, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import (mean_squared_error, mean_absolute_error,
                             r2_score, median_absolute_error)
from xgboost import XGBRegressor

from teaching_data import TEACHING_CATEGORIES, TEACHING_ARTICLES
from player_names import get_player_cn_name, PLAYER_NAMES_CN
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# 应用配置
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nba-pro-2024-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx', 'xls'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录后再访问该页面'

# DeepSeek API 配置（从环境变量读取，不要硬编码密钥）
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_API_URL = os.environ.get('DEEPSEEK_API_URL', 'https://api.deepseek.com/chat/completions')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

# 数据路径
DATA_PATH = os.path.join('static', 'data', 'nba_2022-23_all_stats_with_salary.csv')

# ============================================================
# 数据库模型
# ============================================================
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    comments = db.relationship('Comment', backref='post', lazy=True,
                                cascade='all, delete-orphan')
    likes = db.relationship('PostLike', backref='post', lazy=True,
                             cascade='all, delete-orphan')


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id'),)


class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    role = db.Column(db.String(20), nullable=False)  # user / assistant
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class News(db.Model):
    """篮球新闻模型"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    source = db.Column(db.String(50), default='虎扑')
    summary = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('url', name='uq_news_url'),)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================================================
# 数据加载与预处理
# ============================================================
def load_nba_data():
    """加载NBA数据并清洗"""
    df = pd.read_csv(DATA_PATH)
    df = df.drop(columns=['Unnamed: 0'], errors='ignore')
    df = df.dropna(subset=['Salary', 'PTS', 'MP'])
    df = df[df['MP'] > 0]
    df = df[df['Salary'] > 0]
    df['Salary_M'] = df['Salary'] / 1e6
    # 添加球员中文名列
    df['Player_CN'] = df['Player Name'].apply(get_player_cn_name)
    return df.reset_index(drop=True)


# 全局数据和模型
nba_df = load_nba_data()

# 模型特征定义
NUMERIC_FEATURES = [
    'Age', 'GP', 'GS', 'MP', 'FG', 'FGA', 'FG%', '3P', '3PA', '3P%',
    '2P', '2PA', '2P%', 'eFG%', 'FT', 'FTA', 'FT%', 'ORB', 'DRB', 'TRB',
    'AST', 'STL', 'BLK', 'TOV', 'PF', 'PTS', 'PER', 'TS%', '3PAr', 'FTr',
    'ORB%', 'DRB%', 'TRB%', 'AST%', 'STL%', 'BLK%', 'TOV%', 'USG%',
    'OWS', 'DWS', 'WS', 'WS/48', 'OBPM', 'DBPM', 'BPM', 'VORP'
]
CATEGORICAL_FEATURES = ['Position']
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = 'Salary'


def build_model():
    """构建并训练XGBoost薪资预测模型"""
    df = nba_df.copy()
    X = df[ALL_FEATURES]
    y = np.log1p(df[TARGET])

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), NUMERIC_FEATURES),
            ('cat', OneHotEncoder(drop='first', sparse_output=False,
                                  handle_unknown='ignore'), CATEGORICAL_FEATURES)
        ])

    model = Pipeline([
        ('preprocessor', preprocessor),
        ('regressor', XGBRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            verbosity=0
        ))
    ])

    model.fit(X, y)
    return model


def evaluate_model(model):
    """模型评估，返回各项指标"""
    df = nba_df.copy()
    X = df[ALL_FEATURES]
    y = df[TARGET]
    y_log = np.log1p(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_log, test_size=0.2, random_state=42)

    model.fit(X_train, y_train)
    y_pred_log = model.predict(X_test)
    y_pred = np.expm1(y_pred_log)
    y_test_orig = np.expm1(y_test)

    return {
        'rmse': np.sqrt(mean_squared_error(y_test_orig, y_pred)),
        'mae': mean_absolute_error(y_test_orig, y_pred),
        'r2': r2_score(y_test_orig, y_pred),
        'medae': median_absolute_error(y_test_orig, y_pred),
        'mape': np.mean(np.abs((y_test_orig - y_pred) / y_test_orig)) * 100
    }


# 全局模型
salary_model = build_model()
model_metrics = evaluate_model(salary_model)
# 重新在全量数据上训练
salary_model = build_model()


def get_feature_importance(model, top_n=20):
    """获取特征重要性"""
    regressor = model.named_steps['regressor']
    preprocessor = model.named_steps['preprocessor']

    cat_features = preprocessor.named_transformers_['cat'].get_feature_names_out(CATEGORICAL_FEATURES)
    all_names = NUMERIC_FEATURES + list(cat_features)

    importances = regressor.feature_importances_
    feat_imp = sorted(zip(all_names, importances), key=lambda x: x[1], reverse=True)
    return feat_imp[:top_n]

# ============================================================
# DeepSeek AI 集成
# ============================================================
SYSTEM_PROMPT = """你是一位专业的NBA篮球数据分析师，名叫"篮智AI"。
你精通NBA球员数据分析、薪资结构、战术体系和球员评价。
请用专业但易懂的语言回答用户的问题，可以引用具体数据和案例。
回答要简洁有力，重点突出。如果用户问的是数据相关问题，可以给出分析结论。
当前数据集是2022-23赛季NBA球员数据，包含467名球员的52项技术统计和薪资信息。"""


def deepseek_chat(messages, temperature=0.7):
    """调用DeepSeek API"""
    headers = {
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': DEEPSEEK_MODEL,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': 2000,
        'stream': False
    }
    try:
        resp = requests.post(DEEPSEEK_API_URL, headers=headers,
                             json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']
    except Exception as e:
        return f"AI服务暂时不可用，请稍后再试。错误信息：{str(e)}"


def get_player_stats_context(player_name=None):
    """获取球员数据上下文，用于AI回答"""
    if player_name:
        player = nba_df[nba_df['Player Name'].str.contains(player_name, case=False, na=False)]
        if not player.empty:
            p = player.iloc[0]
            return (f"{p['Player Name']}（{p['Team']}，{p['Position']}）："
                    f"场均{p['PTS']}分{p['TRB']}篮板{p['AST']}助攻，"
                    f"命中率{p['FG%']*100:.1f}%，三分命中率{p['3P%']*100:.1f}%，"
                    f"PER {p['PER']}，WS {p['WS']}，VORP {p['VORP']}，"
                    f"薪资${p['Salary']/1e6:.2f}M。")
    return None

# ============================================================
# 篮球新闻爬取
# ============================================================
from bs4 import BeautifulSoup

SCRAPE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

news_cache = {'data': [], 'last_update': None}

def scrape_hupu_news():
    news_list = []
    try:
        resp = requests.get('https://nba.hupu.com/', headers=SCRAPE_HEADERS, timeout=15)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        seen_urls = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            if 'hupu.com' not in href:
                continue
            if any(s in title for s in ['登录','注册','首页','更多','视频','图片','招聘','客户端']):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            news_list.append({'title': title, 'url': href, 'source': '虎扑'})
            if len(news_list) >= 100:
                break
    except Exception as e:
        print(f'新闻爬取失败: {e}')
    return news_list

def get_cached_news():
    now = datetime.utcnow()
    if news_cache['data'] and news_cache['last_update'] and (now - news_cache['last_update']).total_seconds() < 1800:
        return news_cache['data']
    if not news_cache['data']:
        db_news = News.query.order_by(News.published_at.desc()).limit(100).all()
        if db_news:
            news_cache['data'] = [{'title': n.title, 'url': n.url, 'source': n.source} for n in db_news]
            news_cache['last_update'] = now
    return news_cache['data']

def save_news_to_db(news_list):
    saved = 0
    for news in news_list:
        if not News.query.filter_by(url=news['url']).first():
            db.session.add(News(title=news['title'], url=news['url'], source=news.get('source', '虎扑')))
            saved += 1
    db.session.commit()
    return saved

# 页面路由
# ============================================================
@app.route('/')
def index():
    """首页 - 数据仪表盘"""
    total_players = len(nba_df)
    avg_salary = nba_df['Salary'].mean()
    max_salary = nba_df['Salary'].max()
    max_player = nba_df.loc[nba_df['Salary'].idxmax(), 'Player Name']
    avg_pts = nba_df['PTS'].mean()

    # 薪资Top10
    top10_salary = nba_df.nlargest(10, 'Salary')[
        ['Player Name', 'Player_CN', 'Team', 'Position', 'Salary', 'PTS', 'PER']
    ].to_dict('records')

    # 得分Top10
    top10_pts = nba_df.nlargest(10, 'PTS')[
        ['Player Name', 'Player_CN', 'Team', 'Position', 'PTS', 'Salary', 'PER']
    ].to_dict('records')

    stats = {
        'total_players': total_players,
        'avg_salary': avg_salary,
        'max_salary': max_salary,
        'max_player': max_player,
        'avg_pts': avg_pts,
        'model_r2': model_metrics['r2'],
        'model_mae': model_metrics['mae']
    }

    return render_template('index.html', stats=stats,
                           top10_salary=top10_salary,
                           top10_pts=top10_pts)


@app.route('/players')
def players():
    """球员数据浏览页"""
    positions = sorted(nba_df['Position'].unique().tolist())
    teams = sorted(nba_df['Team'].unique().tolist())
    return render_template('players.html', positions=positions, teams=teams)


@app.route('/prediction')
def prediction():
    """薪资预测页"""
    positions = sorted(nba_df['Position'].unique().tolist())
    # 默认值：联盟平均
    defaults = {
        'Age': int(nba_df['Age'].mean()),
        'GP': int(nba_df['GP'].mean()),
        'GS': int(nba_df['GS'].mean()),
        'MP': round(nba_df['MP'].mean(), 1),
        'PTS': round(nba_df['PTS'].mean(), 1),
        'TRB': round(nba_df['TRB'].mean(), 1),
        'AST': round(nba_df['AST'].mean(), 1),
        'STL': round(nba_df['STL'].mean(), 1),
        'BLK': round(nba_df['BLK'].mean(), 1),
        'FG%': round(nba_df['FG%'].mean(), 3),
        '3P%': round(nba_df['3P%'].mean(), 3),
        'FT%': round(nba_df['FT%'].mean(), 3),
        'PER': round(nba_df['PER'].mean(), 1),
        'WS': round(nba_df['WS'].mean(), 1),
        'USG%': round(nba_df['USG%'].mean(), 1),
        'VORP': round(nba_df['VORP'].mean(), 1),
        'BPM': round(nba_df['BPM'].mean(), 1),
        'TS%': round(nba_df['TS%'].mean(), 3),
        'Position': 'SG'
    }
    feature_imp = get_feature_importance(salary_model, top_n=15)
    return render_template('prediction.html', positions=positions,
                           defaults=defaults, metrics=model_metrics,
                           feature_imp=feature_imp)


@app.route('/visualization')
def visualization():
    """数据可视化页"""
    positions = sorted(nba_df['Position'].unique().tolist())
    return render_template('visualization.html', positions=positions)


@app.route('/ai-chat')
def ai_chat():
    """AI智能助手页"""
    return render_template('ai_chat.html')


@app.route('/forum')
def forum():
    """论坛页"""
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    return render_template('forum.html', posts=posts)


@app.route('/forum/post/<int:post_id>')
def forum_post(post_id):
    """帖子详情页"""
    post = Post.query.get_or_404(post_id)
    post.views += 1
    db.session.commit()
    comments = Comment.query.filter_by(post_id=post_id).order_by(
        Comment.created_at.asc()).all()
    like_count = PostLike.query.filter_by(post_id=post_id).count()
    return render_template('forum_post.html', post=post, comments=comments,
                           like_count=like_count)


@app.route('/upload')
@login_required
def upload():
    """数据上传页"""
    return render_template('upload.html')


# ============================================================
# 用户认证路由
# ============================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
            return redirect(url_for('register'))

        user = User(username=username, email=email or None)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('用户名或密码错误', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ============================================================
# API 路由
# ============================================================
@app.route('/api/players')
def api_players():
    """球员数据API - 支持搜索、筛选、排序、分页"""
    search = request.args.get('search', '').strip()
    position = request.args.get('position', '')
    team = request.args.get('team', '')
    sort_by = request.args.get('sort_by', 'Salary')
    sort_order = request.args.get('sort_order', 'desc')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    df = nba_df.copy()

    if search:
        df = df[df['Player Name'].str.contains(search, case=False, na=False)]
    if position and position != 'all':
        df = df[df['Position'] == position]
    if team and team != 'all':
        df = df[df['Team'] == team]

    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=(sort_order == 'asc'))

    total = len(df)
    start = (page - 1) * per_page
    end = start + per_page
    page_data = df.iloc[start:end]

    # 选择返回的列
    display_cols = ['Player Name', 'Player_CN', 'Team', 'Position', 'Age', 'GP', 'MP',
                    'PTS', 'TRB', 'AST', 'STL', 'BLK', 'FG%', '3P%',
                    'PER', 'WS', 'VORP', 'Salary', 'Salary_M']
    available_cols = [c for c in display_cols if c in df.columns]

    records = page_data[available_cols].to_dict('records')
    # 处理NaN
    for r in records:
        for k, v in r.items():
            if pd.isna(v):
                r[k] = None

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'data': records
    })


@app.route('/api/player/<name>')
def api_player_detail(name):
    """球员详情API"""
    player = nba_df[nba_df['Player Name'] == name]
    if player.empty:
        # 模糊匹配
        player = nba_df[nba_df['Player Name'].str.contains(name, case=False, na=False)]
    if player.empty:
        return jsonify({'error': '球员未找到'}), 404

    p = player.iloc[0].to_dict()
    # 处理NaN
    for k, v in p.items():
        if pd.isna(v):
            p[k] = None
    return jsonify(p)


@app.route('/api/predict', methods=['POST'])
def api_predict():
    """薪资预测API"""
    data = request.get_json()

    # 构建输入DataFrame，使用所有特征，缺失值用均值填充
    input_data = {}
    for feat in NUMERIC_FEATURES:
        if feat in data and data[feat] is not None:
            input_data[feat] = float(data[feat])
        else:
            input_data[feat] = nba_df[feat].mean()

    input_data['Position'] = data.get('Position', 'SG')

    input_df = pd.DataFrame([input_data])

    try:
        log_pred = salary_model.predict(input_df)[0]
        prediction = np.expm1(log_pred)

        # 计算置信区间（基于模型残差）
        df = nba_df.copy()
        y_true = df[TARGET]
        y_pred_all = np.expm1(salary_model.predict(df[ALL_FEATURES]))
        residuals = y_true - y_pred_all
        std_resid = np.std(residuals)

        return jsonify({
            'prediction': float(prediction),
            'prediction_m': float(prediction / 1e6),
            'confidence_low': float(max(0, prediction - 1.96 * std_resid)),
            'confidence_high': float(prediction + 1.96 * std_resid),
            'input': input_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/chart/<chart_type>')
def api_chart(chart_type):
    """可视化图表数据API"""
    df = nba_df.copy()

    if chart_type == 'salary_distribution':
        # 薪资分布直方图
        bins = [0, 1, 2, 5, 10, 15, 20, 30, 50]
        labels = ['<1M', '1-2M', '2-5M', '5-10M', '10-15M', '15-20M', '20-30M', '>30M']
        df['salary_bin'] = pd.cut(df['Salary_M'], bins=bins, labels=labels)
        counts = df['salary_bin'].value_counts().sort_index()
        return jsonify({'labels': list(counts.index), 'values': counts.tolist()})

    elif chart_type == 'salary_by_position':
        # 各位置平均薪资
        pos_salary = df.groupby('Position')['Salary_M'].agg(['mean', 'median', 'count']).sort_values('mean', ascending=False)
        return jsonify({
            'positions': pos_salary.index.tolist(),
            'avg_salary': [round(x, 2) for x in pos_salary['mean'].tolist()],
            'median_salary': [round(x, 2) for x in pos_salary['median_salary'].tolist()],
            'count': pos_salary['count'].tolist()
        })

    elif chart_type == 'pts_vs_salary':
        # 得分vs薪资散点
        sample = df.sample(min(200, len(df)), random_state=42)
        data = []
        for _, row in sample.iterrows():
            data.append({
                'name': row['Player_CN'], 'name_en': row['Player Name'],
                'x': round(row['PTS'], 1),
                'y': round(row['Salary_M'], 2),
                'position': row['Position'],
                'team': row['Team']
            })
        return jsonify({'data': data})

    elif chart_type == 'team_salary':
        # 各球队薪资总和
        team_salary = df.groupby('Team')['Salary'].sum().sort_values(ascending=False)
        return jsonify({
            'teams': team_salary.index.tolist(),
            'total_salary': [round(x / 1e6, 2) for x in team_salary.tolist()]
        })

    elif chart_type == 'age_salary':
        # 年龄与薪资关系
        age_salary = df.groupby('Age')['Salary_M'].agg(['mean', 'count']).reset_index()
        age_salary = age_salary[age_salary['count'] >= 3]
        return jsonify({
            'ages': age_salary['Age'].tolist(),
            'avg_salary': [round(x, 2) for x in age_salary['mean'].tolist()]
        })

    elif chart_type == 'per_salary':
        # PER与薪资散点
        sample = df.sample(min(200, len(df)), random_state=42)
        data = []
        for _, row in sample.iterrows():
            data.append({
                'name': row['Player_CN'], 'name_en': row['Player Name'],
                'x': round(row['PER'], 1),
                'y': round(row['Salary_M'], 2),
                'position': row['Position']
            })
        return jsonify({'data': data})

    elif chart_type == 'radar':
        # 雷达图：各位置平均能力
        radar_cols = ['PTS', 'TRB', 'AST', 'STL', 'BLK', 'PER']
        pos_radar = df.groupby('Position')[radar_cols].mean()
        # 归一化
        for col in radar_cols:
            pos_radar[col] = pos_radar[col] / pos_radar[col].max() * 100
        result = {'indicators': radar_cols}
        for pos in pos_radar.index:
            result[pos] = [round(x, 1) for x in pos_radar.loc[pos].tolist()]
        return jsonify(result)

    elif chart_type == 'feature_importance':
        feat_imp = get_feature_importance(salary_model, top_n=20)
        return jsonify({
            'features': [x[0] for x in feat_imp],
            'importance': [round(float(x[1]), 4) for x in feat_imp]
        })

    else:
        return jsonify({'error': '未知图表类型'}), 404


@app.route('/api/ai-chat', methods=['POST'])
def api_ai_chat():
    """AI聊天API"""
    data = request.get_json()
    user_message = data.get('message', '').strip()
    history = data.get('history', [])

    if not user_message:
        return jsonify({'error': '消息不能为空'}), 400

    # 构建消息列表
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    # 尝试从问题中提取球员名，添加上下文
    context = None
    for name in nba_df['Player Name'].tolist():
        first_name = name.split()[0] if name else ''
        if first_name and first_name.lower() in user_message.lower():
            context = get_player_stats_context(first_name)
            break

    if context:
        messages.append({'role': 'system',
                         'content': f'参考数据：{context}'})

    # 添加历史消息（最多保留10轮）
    for msg in history[-10:]:
        messages.append({'role': msg['role'], 'content': msg['content']})

    messages.append({'role': 'user', 'content': user_message})

    # 调用DeepSeek
    response = deepseek_chat(messages)

    # 保存聊天记录（如果用户已登录）
    if current_user.is_authenticated:
        user_msg = ChatHistory(user_id=current_user.id, role='user',
                                content=user_message)
        ai_msg = ChatHistory(user_id=current_user.id, role='assistant',
                              content=response)
        db.session.add_all([user_msg, ai_msg])
        db.session.commit()

    return jsonify({'response': response})


@app.route('/api/stats/summary')
def api_stats_summary():
    """统计摘要API"""
    return jsonify({
        'total_players': len(nba_df),
        'total_salary': float(nba_df['Salary'].sum()),
        'avg_salary': float(nba_df['Salary'].mean()),
        'median_salary': float(nba_df['Salary'].median()),
        'max_salary': float(nba_df['Salary'].max()),
        'min_salary': float(nba_df['Salary'].min()),
        'avg_pts': float(nba_df['PTS'].mean()),
        'avg_per': float(nba_df['PER'].mean()),
        'num_teams': nba_df['Team'].nunique(),
        'num_positions': nba_df['Position'].nunique(),
        'model_r2': float(model_metrics['r2']),
        'model_mae': float(model_metrics['mae'])
    })


# ============================================================
# 文件上传API
# ============================================================
@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件格式，请上传CSV或Excel文件'}), 400

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # 读取数据
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        # 生成预览
        preview_cols = list(df.columns)[:15]  # 最多显示15列
        preview_data = df[preview_cols].head(5).fillna('').values.tolist()

        # 数值列统计
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        stats = {}
        for col in numeric_cols[:10]:
            stats[col] = {
                'mean': round(float(df[col].mean()), 4) if not df[col].isna().all() else None,
                'std': round(float(df[col].std()), 4) if not df[col].isna().all() else None,
                'min': round(float(df[col].min()), 4) if not df[col].isna().all() else None,
                'max': round(float(df[col].max()), 4) if not df[col].isna().all() else None
            }

        return jsonify({
            'filename': filename,
            'rows': len(df),
            'columns': len(df.columns),
            'column_names': list(df.columns),
            'numeric_columns': numeric_cols,
            'preview': {
                'columns': preview_cols,
                'data': preview_data
            },
            'statistics': stats
        })
    except Exception as e:
        return jsonify({'error': f'文件处理失败: {str(e)}'}), 500


# ============================================================
# 论坛API
# ============================================================
@app.route('/api/forum/post', methods=['POST'])
@login_required
def api_create_post():
    data = request.get_json()
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({'error': '标题和内容不能为空'}), 400

    post = Post(title=title, content=content, user_id=current_user.id)
    db.session.add(post)
    db.session.commit()
    return jsonify({'id': post.id, 'message': '发布成功'})


@app.route('/api/forum/post/<int:post_id>/comment', methods=['POST'])
@login_required
def api_add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    data = request.get_json()
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'error': '评论内容不能为空'}), 400

    comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
    db.session.add(comment)
    db.session.commit()
    return jsonify({'id': comment.id, 'message': '评论成功'})


@app.route('/api/forum/post/<int:post_id>/like', methods=['POST'])
@login_required
def api_like_post(post_id):
    post = Post.query.get_or_404(post_id)
    existing = PostLike.query.filter_by(user_id=current_user.id,
                                         post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        like = PostLike(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        liked = True
    db.session.commit()
    count = PostLike.query.filter_by(post_id=post_id).count()
    return jsonify({'liked': liked, 'count': count})


# ============================================================


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = {'players': [], 'news': [], 'teaching': [], 'query': query, 'total': 0}
    
    if query:
        # 搜索球员
        try:
            mask = nba_df['Player Name'].str.contains(query, case=False, na=False) | \
                   nba_df['Team'].str.contains(query, case=False, na=False)
            player_matches = nba_df[mask].head(10)
            for _, row in player_matches.iterrows():
                results['players'].append({
                    'name': row['Player_CN'], 'name_en': row['Player Name'],
                    'team': row['Team'],
                    'position': row['Position'],
                    'points': row.get('PTS', 0),
                    'salary': row.get('Salary', 0)
                })
        except Exception:
            pass
        
        # 搜索新闻
        try:
            news_matches = News.query.filter(News.title.contains(query)).limit(10).all()
            for n in news_matches:
                results['news'].append({'title': n.title, 'url': n.url, 'source': n.source})
        except Exception:
            pass
        
        # 搜索教学文章
        for article in TEACHING_ARTICLES:
            if query.lower() in article['title'].lower() or query.lower() in article['summary'].lower():
                cat = next((c for c in TEACHING_CATEGORIES if c['id'] == article['category']), None)
                results['teaching'].append({
                    'id': article['id'],
                    'title': article['title'],
                    'category': cat['name'] if cat else '未分类',
                    'summary': article['summary']
                })
        
        results['total'] = len(results['players']) + len(results['news']) + len(results['teaching'])
    
    return render_template('search.html', **results)


@app.route('/compare')
def compare():
    return render_template('compare.html')


@app.route('/news')
def news():
    news_list = get_cached_news()
    return render_template('news.html', news_list=news_list)

@app.route('/api/news/refresh', methods=['POST'])
def api_refresh_news():
    try:
        news_list = scrape_hupu_news()
        saved = save_news_to_db(news_list)
        news_cache['data'] = news_list
        news_cache['last_update'] = datetime.utcnow()
        return jsonify({'success': True, 'count': len(news_list), 'saved': saved, 'news': news_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/teaching')
def teaching():
    return render_template('teaching.html', categories=TEACHING_CATEGORIES, articles=TEACHING_ARTICLES)

@app.route('/teaching/<int:article_id>')
def teaching_detail(article_id):
    article = next((a for a in TEACHING_ARTICLES if a['id'] == article_id), None)
    if not article:
        return redirect(url_for('teaching'))
    category = next((c for c in TEACHING_CATEGORIES if c['id'] == article['category']), None)
    related = [a for a in TEACHING_ARTICLES if a['category'] == article['category'] and a['id'] != article_id][:3]
    return render_template('teaching_detail.html', article=article, category=category, related=related)

# 工具函数
# ============================================================
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}


# ============================================================
# 启动
# ============================================================
def init_db():
    with app.app_context():
        db.create_all()
        # 创建默认管理员账号（如果不存在）
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@nba.com')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('默认管理员账号已创建: admin / admin123')


if __name__ == '__main__':
    init_db()
    print(f"NBA数据分析平台 Pro版 启动中...")
    print(f"球员数据: {len(nba_df)} 名球员, {len(ALL_FEATURES)} 项特征")
    print(f"模型R²: {model_metrics['r2']:.4f}, MAE: ${model_metrics['mae']/1e6:.2f}M")
    print(f"访问地址: http://127.0.0.1:5002")
    app.run(debug=False, host='0.0.0.0', port=5002, threaded=True)

/* ============================================================
   NBA数据分析平台 Pro - 主JavaScript
   ============================================================ */

// 全局配置
const API_BASE = '';

// ============================================================
// 通用工具函数
// ============================================================

// 格式化薪资
function formatSalary(value) {
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e3) return '$' + (value / 1e3).toFixed(1) + 'K';
    return '$' + value.toFixed(0);
}

// 格式化数字
function formatNumber(value, decimals = 1) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    return Number(value).toFixed(decimals);
}

// 格式化百分比
function formatPercent(value, decimals = 1) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    return (value * 100).toFixed(decimals) + '%';
}

// 防抖
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// API请求封装
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: { 'Content-Type': 'application/json' },
    };
    const mergedOptions = { ...defaultOptions, ...options };
    if (mergedOptions.body && typeof mergedOptions.body === 'object') {
        mergedOptions.body = JSON.stringify(mergedOptions.body);
    }

    try {
        const response = await fetch(url, mergedOptions);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || '请求失败');
        }
        return data;
    } catch (error) {
        console.error('API请求错误:', error);
        throw error;
    }
}

// GET请求
function apiGet(url, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const fullUrl = queryString ? `${url}?${queryString}` : url;
    return apiRequest(fullUrl);
}

// POST请求
function apiPost(url, data = {}) {
    return apiRequest(url, { method: 'POST', body: data });
}

// ============================================================
// 侧边栏切换
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebarToggle');

    if (toggle && sidebar) {
        toggle.addEventListener('click', function() {
            sidebar.classList.toggle('open');
        });
    }

    // 点击内容区关闭侧边栏（移动端）
    document.querySelector('.main-content').addEventListener('click', function(e) {
        if (window.innerWidth <= 768 && sidebar.classList.contains('open')
            && !e.target.closest('.sidebar') && !e.target.closest('.sidebar-toggle')) {
            sidebar.classList.remove('open');
        }
    });
});

// ============================================================
// ECharts 通用配置
// ============================================================
const EChartsTheme = {
    backgroundColor: 'transparent',
    textStyle: {
        color: '#94a3b8',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    },
    title: {
        textStyle: { color: '#f1f5f9', fontSize: 16, fontWeight: 600 },
        subtextStyle: { color: '#64748b' }
    },
    legend: {
        textStyle: { color: '#94a3b8' },
        itemWidth: 14,
        itemHeight: 10
    },
    tooltip: {
        backgroundColor: 'rgba(26, 35, 50, 0.95)',
        borderColor: '#2a3548',
        textStyle: { color: '#f1f5f9', fontSize: 13 },
        padding: [10, 14],
        extraCssText: 'border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.4);'
    },
    grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '15%',
        containLabel: true
    },
    categoryAxis: {
        axisLine: { lineStyle: { color: '#2a3548' } },
        axisTick: { show: false },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { show: false }
    },
    valueAxis: {
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } }
    }
};

// 应用主题到图表配置
function applyTheme(option) {
    return {
        ...EChartsTheme,
        ...option
    };
}

// 渐变色
const gradientColors = {
    blue: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(59, 130, 246, 0.8)' },
        { offset: 1, color: 'rgba(59, 130, 246, 0.1)' }
    ]),
    purple: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(139, 92, 246, 0.8)' },
        { offset: 1, color: 'rgba(139, 92, 246, 0.1)' }
    ]),
    green: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(16, 185, 129, 0.8)' },
        { offset: 1, color: 'rgba(16, 185, 129, 0.1)' }
    ]),
    orange: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(245, 158, 11, 0.8)' },
        { offset: 1, color: 'rgba(245, 158, 11, 0.1)' }
    ])
};

// 颜色调色板
const colorPalette = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444',
                       '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#6366f1'];

// ============================================================
// 通用图表加载
// ============================================================
async function loadChart(containerId, chartType, optionBuilder) {
    const container = document.getElementById(containerId);
    if (!container) return null;

    const chart = echarts.init(container);
    chart.showLoading({
        text: '加载中...',
        color: '#3b82f6',
        textColor: '#94a3b8',
        maskColor: 'rgba(10, 14, 23, 0.5)'
    });

    try {
        const data = await apiGet(`/api/chart/${chartType}`);
        const option = optionBuilder(data);
        chart.setOption(applyTheme(option));
    } catch (error) {
        console.error(`图表加载失败 [${chartType}]:`, error);
        chart.setOption(applyTheme({
            title: { text: '数据加载失败', left: 'center', top: 'center',
                     textStyle: { color: '#64748b', fontSize: 14 } }
        }));
    } finally {
        chart.hideLoading();
    }

    // 响应式
    window.addEventListener('resize', () => chart.resize());
    return chart;
}

// ============================================================
// 提示消息
// ============================================================
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        color: white;
        font-size: 14px;
        font-weight: 500;
        z-index: 9999;
        animation: toastIn 0.3s ease;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    `;

    const colors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    };
    toast.style.background = colors[type] || colors.info;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 添加toast动画
const toastStyle = document.createElement('style');
toastStyle.textContent = `
    @keyframes toastIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes toastOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(toastStyle);

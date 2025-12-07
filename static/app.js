/**
 * 小红书收藏夹本地化 - 前端应用 v2.0
 */

// ================= 状态管理 =================
const state = {
    currentAlbum: '全部笔记',
    currentPage: 1,
    pageSize: 24,
    totalNotes: 0,
    searchKeyword: '',
    filterType: 'all',
    filterLearning: 'all',
    viewMode: 'grid',
    notes: [],
    currentNoteDetail: null,
    mediaIndex: 0,
    isLoading: false,
    onlyDownloaded: false
};

// ================= DOM 元素 =================
const elements = {
    albumList: document.getElementById('album-list'),
    totalCount: document.getElementById('total-count'),
    downloadedCount: document.getElementById('downloaded-count'),
    pageTitle: document.getElementById('page-title'),
    pageCount: document.getElementById('page-count'),
    searchInput: document.getElementById('search-input'),
    searchClear: document.getElementById('search-clear'),
    filterType: document.getElementById('filter-type'),
    filterLearning: document.getElementById('filter-learning'),
    notesGrid: document.getElementById('notes-grid'),
    loadMore: document.getElementById('load-more'),
    loadMoreBtn: document.getElementById('load-more-btn'),
    emptyState: document.getElementById('empty-state'),
    loadingState: document.getElementById('loading-state'),
    modalOverlay: document.getElementById('modal-overlay'),
    modalClose: document.getElementById('modal-close'),
    mediaContainer: document.getElementById('media-container'),
    mediaNav: document.getElementById('media-nav'),
    mediaPrev: document.getElementById('media-prev'),
    mediaNext: document.getElementById('media-next'),
    mediaIndicator: document.getElementById('media-indicator'),
    toastContainer: document.getElementById('toast-container'),
    // 统计
    statsDownloaded: document.getElementById('stats-downloaded'),
    statsPending: document.getElementById('stats-pending'),
    statsStorage: document.getElementById('stats-storage'),
    progressFill: document.getElementById('progress-fill'),
};

// ================= API 请求 =================
const api = {
    async getAlbums() {
        const res = await fetch('/api/albums');
        return res.json();
    },

    async getNotes(album = null, page = 1, pageSize = 24, learningStatus = null) {
        const params = new URLSearchParams({ page, page_size: pageSize });
        if (album && album !== '全部笔记' && album !== '已下载' && album !== '星标') {
            params.append('album', album);
        } else if (album === '星标') {
            params.append('album', '星标');
        }
        if (learningStatus) {
            params.append('learning_status', learningStatus);
        }
        const res = await fetch(`/api/notes?${params}`);
        return res.json();
    },

    async searchNotes(keyword, page = 1, pageSize = 24) {
        const params = new URLSearchParams({ q: keyword, page, page_size: pageSize });
        const res = await fetch(`/api/search?${params}`);
        return res.json();
    },

    async getNoteDetail(noteId) {
        const res = await fetch(`/api/notes/${noteId}`);
        return res.json();
    },
    
    async getStats() {
        const res = await fetch('/api/stats');
        return res.json();
    },
    
    async getLocalAlbums() {
        const res = await fetch('/api/local-albums');
        return res.json();
    },
    
    async createCustomAlbum(name) {
        const res = await fetch('/api/custom-albums', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '创建失败');
        }
        return res.json();
    },
    
    async getCustomAlbums() {
        const res = await fetch('/api/custom-albums');
        return res.json();
    },
    
    async moveOrCopyNote(noteId, targetAlbum, operation) {
        const res = await fetch(`/api/notes/${noteId}/move`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_album: targetAlbum, operation })
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '操作失败');
        }
        return res.json();
    },
    
    async toggleLearningStatus(noteId) {
        const res = await fetch(`/api/notes/${noteId}/learning-status`, {
            method: 'POST'
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '操作失败');
        }
        return res.json();
    },
    
    async toggleStarredStatus(noteId) {
        const res = await fetch(`/api/notes/${noteId}/starred-status`, {
            method: 'POST'
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || '操作失败');
        }
        return res.json();
    }
};

// ================= 渲染函数 =================
function renderAlbums(albums) {
    const albumList = elements.albumList;
    albumList.innerHTML = '';

    // 更新总数
    const totalAlbum = albums.find(a => a.name === '全部笔记');
    if (totalAlbum) {
        elements.totalCount.textContent = totalAlbum.count;
    }
    
    // 更新已下载数量
    const downloadedAlbum = albums.find(a => a.name === '已下载');
    if (downloadedAlbum) {
        elements.downloadedCount.textContent = downloadedAlbum.count;
    }
    
    // 更新星标数量
    const starredAlbum = albums.find(a => a.name === '星标');
    const starredCountEl = document.getElementById('starred-count');
    if (starredCountEl && starredAlbum) {
        starredCountEl.textContent = starredAlbum.count;
    }

    // 渲染专辑列表（跳过"全部笔记"、"已下载"和"星标"）
    albums.filter(a => a.name !== '全部笔记' && a.name !== '已下载' && a.name !== '星标').forEach(album => {
        const item = document.createElement('div');
        item.className = 'nav-item';
        item.dataset.album = album.name;
        item.innerHTML = `
            <span class="nav-icon">📁</span>
            <span class="nav-text" title="${escapeHtml(album.name)}">${escapeHtml(album.name)}</span>
            <span class="nav-count">${album.count}</span>
        `;
        item.addEventListener('click', () => selectAlbum(album.name));
        albumList.appendChild(item);
    });
}

function renderNotes(notes, append = false) {
    const grid = elements.notesGrid;
    
    if (!append) {
        grid.innerHTML = '';
    }

    // 应用筛选
    let filteredNotes = notes;
    
    if (state.filterType !== 'all') {
        filteredNotes = notes.filter(note => {
            if (state.filterType === 'video') return note.type === 'video';
            if (state.filterType === 'normal') return note.type !== 'video';
            return true;
        });
    }
    
    if (state.filterLearning !== 'all') {
        filteredNotes = filteredNotes.filter(note => {
            if (state.filterLearning === 'learned') return note.isLearned === true;
            if (state.filterLearning === 'unlearned') return note.isLearned !== true;
            return true;
        });
    }
    
    if (state.onlyDownloaded) {
        filteredNotes = filteredNotes.filter(note => note.hasLocal);
    }

    if (filteredNotes.length === 0 && !append) {
        elements.emptyState.style.display = 'block';
        elements.loadMore.style.display = 'none';
        return;
    }

    elements.emptyState.style.display = 'none';

    filteredNotes.forEach(note => {
        const card = createNoteCard(note);
        grid.appendChild(card);
    });

    // 更新数量显示
    elements.pageCount.textContent = `共 ${state.totalNotes} 条`;

    // 更新加载更多按钮状态
    const loadedCount = grid.children.length;
    if (loadedCount >= state.totalNotes) {
        elements.loadMore.style.display = 'none';
    } else {
        elements.loadMore.style.display = 'block';
    }
}

function createNoteCard(note) {
    const card = document.createElement('div');
    card.className = 'note-card fade-in';
    
    const noteId = note.id.split('?')[0];
    const isVideo = note.type === 'video';
    
    card.innerHTML = `
        <div class="note-cover">
            <img src="${escapeHtml(note.cover)}" alt="${escapeHtml(note.title)}" loading="lazy" 
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23f5f5f5%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 text-anchor=%22middle%22 fill=%22%23ccc%22 font-size=%2212%22>无封面</text></svg>'">
            ${isVideo ? '<span class="note-type-badge">▶ 视频</span>' : ''}
            ${note.isLearned ? '<span class="note-learning-badge learned">✓ 已学习</span>' : '<span class="note-learning-badge unlearned">○ 未学习</span>'}
            ${note.isStarred ? '<span class="note-starred-badge">⭐</span>' : ''}
        </div>
        <div class="note-info">
            <div class="note-title">${escapeHtml(note.title) || '无标题'}</div>
            <div class="note-author">
                <img class="note-avatar" src="${escapeHtml(note.authorAvatar)}" alt="" 
                     onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><circle fill=%22%23e0e0e0%22 cx=%2220%22 cy=%2220%22 r=%2220%22/><circle fill=%22%23bbb%22 cx=%2220%22 cy=%2216%22 r=%228%22/><ellipse fill=%22%23bbb%22 cx=%2220%22 cy=%2236%22 rx=%2212%22 ry=%2210%22/></svg>'">
                <span class="note-author-name">${escapeHtml(note.author) || '未知作者'}</span>
            </div>
            <div class="note-meta">
                <div class="note-meta-left">
                    <span class="note-tag">${escapeHtml(note.album) || '未分类'}</span>
                    ${note.hasLocal ? '<span class="note-local-badge">✓ 已下载</span>' : ''}
                </div>
                <div class="note-stats">
                    <button class="note-action-btn-text" data-note-id="${noteId}" data-action="copy" title="复制到专辑">复制</button>
                    <button class="note-action-btn-text" data-note-id="${noteId}" data-action="move" title="移动到专辑">移动</button>
                    <span>❤️ ${formatNumber(note.likes)}</span>
                </div>
            </div>
        </div>
    `;

    // 点击卡片打开详情
    card.addEventListener('click', (e) => {
        // 如果点击的是操作按钮,不打开详情
        if (e.target.closest('.note-action-btn-text')) {
            e.stopPropagation();
            return;
        }
        openNoteDetail(noteId);
    });
    
    // 绑定操作按钮事件
    const actionBtns = card.querySelectorAll('.note-action-btn-text');
    actionBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const action = btn.dataset.action;
            const noteId = btn.dataset.noteId;
            openAlbumSelector(noteId, action);
        });
    });
    
    return card;
}

function renderNoteDetail(detail) {
    // 作者信息
    document.getElementById('detail-avatar').src = detail.authorAvatar || '';
    document.getElementById('detail-author').textContent = detail.author || '未知作者';
    document.getElementById('detail-album').textContent = detail.album || '';
    
    // 本地状态
    const localBadge = document.getElementById('detail-local-badge');
    if (detail.hasLocal) {
        localBadge.textContent = '已下载';
        localBadge.classList.remove('pending');
    } else {
        localBadge.textContent = '未下载';
        localBadge.classList.add('pending');
    }
    
    // 学习状态按钮
    const learningBtn = document.getElementById('detail-learning-btn');
    if (learningBtn) {
        if (detail.isLearned) {
            learningBtn.textContent = '✓ 已学习';
            learningBtn.className = 'action-btn learning-btn learned';
        } else {
            learningBtn.textContent = '○ 未学习';
            learningBtn.className = 'action-btn learning-btn unlearned';
        }
        learningBtn.dataset.noteId = detail.id;
    }
    
    // 星标按钮
    const starBtn = document.getElementById('detail-star-btn');
    if (starBtn) {
        if (detail.isStarred) {
            starBtn.classList.add('starred');
        } else {
            starBtn.classList.remove('starred');
        }
        starBtn.dataset.noteId = detail.id;
    }
    
    // 标题和内容
    document.getElementById('detail-title').textContent = detail.title || '无标题';
    const descContent = detail.desc || (detail.hasLocal ? '（无文案内容）' : '（未下载到本地，请先爬取笔记详情）');
    document.getElementById('detail-content').textContent = descContent;
    
    // 标签
    const tagsContainer = document.getElementById('detail-tags');
    if (detail.tags && detail.tags.length > 0) {
        tagsContainer.innerHTML = detail.tags.map(tag => 
            `<span class="detail-tag">#${escapeHtml(tag)}</span>`
        ).join('');
        tagsContainer.style.display = 'flex';
    } else {
        tagsContainer.style.display = 'none';
    }
    
    // 统计
    document.getElementById('detail-likes').textContent = formatNumber(detail.likes);
    document.getElementById('detail-collects').textContent = formatNumber(detail.collects);
    document.getElementById('detail-comments').textContent = formatNumber(detail.comments);
    document.getElementById('detail-shares').textContent = formatNumber(detail.shares || 0);
    
    // 链接
    const detailLink = document.getElementById('detail-link');
    if (detailLink) {
        detailLink.href = detail.noteUrl || `https://www.xiaohongshu.com/explore/${detail.id}`;
    }
    
    // 沉浸式查看链接
    const immersiveBtn = document.getElementById('immersive-view');
    if (immersiveBtn) {
        if (detail && detail.id) {
            const viewUrl = `/view/${detail.id}`;
            immersiveBtn.style.display = 'inline-flex';
            
            // 移除 target="_blank"，在当前窗口打开
            immersiveBtn.removeAttribute('target');
            
            // 清除所有之前的事件监听器（通过克隆节点）
            const newBtn = immersiveBtn.cloneNode(true);
            immersiveBtn.parentNode.replaceChild(newBtn, immersiveBtn);
            const btn = document.getElementById('immersive-view');
            
            // 设置 href
            btn.href = viewUrl;
            
            // 添加点击事件处理，使用 window.location 确保正确跳转
            btn.addEventListener('click', function(e) {
                e.preventDefault(); // 阻止默认行为
                if (viewUrl && viewUrl !== '#' && viewUrl !== '/view/') {
                    window.location.href = viewUrl;
                } else {
                    console.error('❌ 沉浸式查看链接无效:', viewUrl);
                }
            });
            
            console.log('✅ 沉浸式查看链接已设置:', viewUrl, '笔记ID:', detail.id);
        } else {
            console.error('❌ 笔记 ID 不存在，无法打开沉浸式查看', detail);
            immersiveBtn.style.display = 'none';
        }
    } else {
        console.error('❌ 找不到沉浸式查看按钮元素');
    }
    
    // 媒体
    state.currentNoteDetail = detail;
    state.mediaIndex = 0;
    renderMedia();
}

function renderMedia() {
    const detail = state.currentNoteDetail;
    if (!detail) return;

    const container = elements.mediaContainer;
    const allMedia = [];
    
    // 视频优先
    if (detail.video) {
        allMedia.push({ type: 'video', url: detail.video });
    }
    
    // 图片
    if (detail.images && detail.images.length > 0) {
        detail.images.forEach(img => {
            allMedia.push({ type: 'image', url: img });
        });
    }

    if (allMedia.length === 0) {
        container.innerHTML = `
            <div style="color: #999; padding: 40px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
                <div>${detail.hasLocal ? '暂无媒体文件' : '请先下载笔记查看完整内容'}</div>
            </div>
        `;
        elements.mediaNav.style.display = 'none';
        return;
    }

    // 确保索引在范围内
    if (state.mediaIndex >= allMedia.length) {
        state.mediaIndex = 0;
    }

    const currentMedia = allMedia[state.mediaIndex];
    
    if (currentMedia.type === 'video') {
        container.innerHTML = `
            <video src="${currentMedia.url}" controls autoplay 
                   style="max-width: 100%; max-height: 100%; border-radius: 8px;">
                您的浏览器不支持视频播放
            </video>
        `;
    } else {
        container.innerHTML = `
            <img src="${currentMedia.url}" alt="笔记图片" 
                 style="max-width: 100%; max-height: 100%; border-radius: 8px;"
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 150%22><rect fill=%22%23f5f5f5%22 width=%22200%22 height=%22150%22/><text x=%22100%22 y=%2280%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%2214%22>加载失败</text></svg>'">
        `;
    }

    // 更新导航
    if (allMedia.length > 1) {
        elements.mediaNav.style.display = 'flex';
        elements.mediaIndicator.textContent = `${state.mediaIndex + 1} / ${allMedia.length}`;
        elements.mediaPrev.disabled = state.mediaIndex === 0;
        elements.mediaNext.disabled = state.mediaIndex === allMedia.length - 1;
    } else {
        elements.mediaNav.style.display = 'none';
    }
}

async function renderStats() {
    try {
        const stats = await api.getStats();
        elements.statsDownloaded.textContent = stats.downloaded_notes;
        elements.statsPending.textContent = stats.pending_notes;
        elements.statsStorage.textContent = `${stats.storage_size_mb} MB`;
        elements.progressFill.style.width = `${stats.download_progress}%`;
        elements.downloadedCount.textContent = stats.downloaded_notes;
    } catch (error) {
        console.error('获取统计信息失败:', error);
    }
}

// ================= 事件处理 =================
function selectAlbum(albumName) {
    state.currentAlbum = albumName;
    state.currentPage = 1;
    state.searchKeyword = '';
    state.onlyDownloaded = albumName === '已下载';
    elements.searchInput.value = '';
    elements.searchClear.style.display = 'none';
    
    // 更新导航选中状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.album === albumName);
    });
    
    // 更新标题
    elements.pageTitle.textContent = albumName;
    
    // 加载笔记
    loadNotes();
}

async function loadNotes(append = false) {
    if (state.isLoading) return;
    state.isLoading = true;
    
    elements.loadMoreBtn.disabled = true;
    elements.loadMoreBtn.textContent = '加载中...';
    
    if (!append) {
        elements.loadingState.style.display = 'block';
        elements.notesGrid.style.opacity = '0.5';
    }

    try {
        let result;
        if (state.searchKeyword) {
            result = await api.searchNotes(state.searchKeyword, state.currentPage, state.pageSize);
        } else {
            let album = null;
            if (state.currentAlbum === '星标') {
                album = '星标';
            } else if (!state.onlyDownloaded && state.currentAlbum !== '全部笔记') {
                album = state.currentAlbum;
            }
            const learningStatus = state.filterLearning !== 'all' ? state.filterLearning : null;
            result = await api.getNotes(album, state.currentPage, state.pageSize, learningStatus);
        }

        state.totalNotes = result.total;
        
        if (append) {
            state.notes = [...state.notes, ...result.notes];
        } else {
            state.notes = result.notes;
        }

        renderNotes(result.notes, append);
    } catch (error) {
        console.error('加载笔记失败:', error);
        showToast('加载笔记失败，请稍后重试', 'error');
    } finally {
        state.isLoading = false;
        elements.loadMoreBtn.disabled = false;
        elements.loadMoreBtn.textContent = '加载更多';
        elements.loadingState.style.display = 'none';
        elements.notesGrid.style.opacity = '1';
    }
}

async function openNoteDetail(noteId) {
    try {
        const detail = await api.getNoteDetail(noteId);
        renderNoteDetail(detail);
        elements.modalOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    } catch (error) {
        console.error('获取笔记详情失败:', error);
        showToast('获取笔记详情失败', 'error');
    }
}

function closeModal() {
    elements.modalOverlay.classList.remove('active');
    document.body.style.overflow = '';
    
    // 停止视频播放
    const video = elements.mediaContainer.querySelector('video');
    if (video) {
        video.pause();
    }
}


function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${type === 'success' ? '✅' : '❌'}</span>
        <span>${message}</span>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function setViewMode(mode) {
    state.viewMode = mode;
    const grid = elements.notesGrid;
    
    if (mode === 'list') {
        grid.classList.add('list-view');
    } else {
        grid.classList.remove('list-view');
    }
    
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === mode);
    });
}

// ================= 工具函数 =================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    const n = typeof num === 'string' ? parseFloat(num) : num;
    if (isNaN(n)) return num;
    if (n >= 10000) {
        return (n / 10000).toFixed(1) + 'w';
    }
    if (n >= 1000) {
        return (n / 1000).toFixed(1) + 'k';
    }
    return n.toString();
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// ================= 专辑管理 =================
let currentOperation = null;  // 'copy' 或 'move'
let currentNoteId = null;

async function openCreateAlbumModal() {
    const modal = document.getElementById('create-album-modal');
    const input = document.getElementById('album-name-input');
    input.value = '';
    modal.style.display = 'flex';
    setTimeout(() => {
        modal.classList.add('active');
        input.focus();
    }, 10);
}

function closeCreateAlbumModal() {
    const modal = document.getElementById('create-album-modal');
    modal.classList.remove('active');
    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
}

async function createAlbum() {
    const input = document.getElementById('album-name-input');
    const name = input.value.trim();
    
    if (!name) {
        showToast('请输入专辑名称', 'error');
        return;
    }
    
    try {
        await api.createCustomAlbum(name);
        showToast('专辑创建成功', 'success');
        closeCreateAlbumModal();
        
        // 重新加载专辑列表
        const albums = await api.getAlbums();
        renderAlbums(albums);
    } catch (error) {
        showToast(error.message || '创建失败', 'error');
    }
}

async function openAlbumSelector(noteId, operation) {
    currentNoteId = noteId;
    currentOperation = operation;
    
    const modal = document.getElementById('select-album-modal');
    const title = document.getElementById('select-album-title');
    const list = document.getElementById('album-select-list');
    
    const titleText = operation === 'copy' ? '复制到专辑' : '移动到专辑';
    const icon = operation === 'copy' ? '📋' : '📁';
    title.innerHTML = `<span class="modal-title-icon">${icon}</span>${titleText}`;
    list.innerHTML = '';
    
    // 获取所有专辑列表（包括原始专辑和自定义专辑）
    try {
        const allAlbums = await api.getAlbums();
        // 过滤掉"全部笔记"和"已下载"
        const availableAlbums = allAlbums.filter(album => 
            album.name !== '全部笔记' && album.name !== '已下载'
        );
        
        if (availableAlbums.length === 0) {
            list.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);">暂无可用专辑</div>';
        } else {
            availableAlbums.forEach(album => {
                const item = document.createElement('div');
                item.className = 'album-select-item';
                item.innerHTML = `
                    <span class="album-select-item-name">${escapeHtml(album.name)}</span>
                    <span class="album-select-item-count">${album.count} 条笔记</span>
                `;
                item.addEventListener('click', () => {
                    moveOrCopyNoteToAlbum(album.name);
                });
                list.appendChild(item);
            });
        }
        
        modal.style.display = 'flex';
        setTimeout(() => {
            modal.classList.add('active');
        }, 10);
    } catch (error) {
        showToast('获取专辑列表失败', 'error');
    }
}

function closeAlbumSelector() {
    const modal = document.getElementById('select-album-modal');
    modal.classList.remove('active');
    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
    currentNoteId = null;
    currentOperation = null;
}

async function moveOrCopyNoteToAlbum(albumName) {
    if (!currentNoteId || !currentOperation) {
        return;
    }
    
    try {
        await api.moveOrCopyNote(currentNoteId, albumName, currentOperation);
        showToast(`笔记已${currentOperation === 'copy' ? '复制' : '移动'}到专辑 ${albumName}`, 'success');
        closeAlbumSelector();
        
        // 如果当前在查看该专辑,刷新笔记列表
        if (state.currentAlbum === albumName || state.currentAlbum === '全部笔记') {
            loadNotes();
        }
        
        // 刷新专辑列表
        const albums = await api.getAlbums();
        renderAlbums(albums);
    } catch (error) {
        showToast(error.message || '操作失败', 'error');
    }
}

// ================= 初始化 =================
async function init() {
    // 加载统计信息
    renderStats();
    
    // 加载专辑列表
    try {
        const albums = await api.getAlbums();
        renderAlbums(albums);
    } catch (error) {
        console.error('加载专辑失败:', error);
    }

    // 加载笔记
    loadNotes();

    // 绑定事件
    
    // 全部笔记点击
    const allNotesNav = document.querySelector('.nav-item[data-album="全部笔记"]');
    if (allNotesNav) {
        allNotesNav.addEventListener('click', () => {
            selectAlbum('全部笔记');
        });
    }
    
    // 已下载点击
    const downloadedNav = document.querySelector('.nav-item[data-album="已下载"]');
    if (downloadedNav) {
        downloadedNav.addEventListener('click', () => {
            selectAlbum('已下载');
        });
    }
    
    // 星标点击
    const starredNav = document.querySelector('.nav-item[data-album="星标"]');
    if (starredNav) {
        starredNav.addEventListener('click', () => {
            selectAlbum('星标');
        });
    }

    // 搜索
    if (elements.searchInput) {
        elements.searchInput.addEventListener('input', debounce((e) => {
        const keyword = e.target.value.trim();
        state.searchKeyword = keyword;
        state.currentPage = 1;
        
        elements.searchClear.style.display = keyword ? 'block' : 'none';
        
        if (keyword) {
            elements.pageTitle.textContent = `搜索: ${keyword}`;
        } else {
            elements.pageTitle.textContent = state.currentAlbum;
        }
        
        loadNotes();
    }, 300));
    }
    
    // 清除搜索
    if (elements.searchClear) {
        elements.searchClear.addEventListener('click', () => {
        elements.searchInput.value = '';
        elements.searchClear.style.display = 'none';
        state.searchKeyword = '';
        state.currentPage = 1;
        elements.pageTitle.textContent = state.currentAlbum;
        loadNotes();
    });
    }
    
    // 类型筛选
    if (elements.filterType) {
        elements.filterType.addEventListener('change', (e) => {
        state.filterType = e.target.value;
        state.currentPage = 1;
        loadNotes();
    });
    }
    
    // 学习状态筛选
    if (elements.filterLearning) {
        elements.filterLearning.addEventListener('change', (e) => {
        state.filterLearning = e.target.value;
        state.currentPage = 1;
        loadNotes();
    });
    }
    
    // 学习状态切换按钮
    const learningBtn = document.getElementById('detail-learning-btn');
    if (learningBtn) {
        learningBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            const noteId = learningBtn.dataset.noteId;
            if (!noteId) return;
            
            try {
                const result = await api.toggleLearningStatus(noteId);
                // 更新按钮状态
                if (result.is_learned) {
                    learningBtn.textContent = '✓ 已学习';
                    learningBtn.className = 'action-btn learning-btn learned';
                } else {
                    learningBtn.textContent = '○ 未学习';
                    learningBtn.className = 'action-btn learning-btn unlearned';
                }
                // 更新详情数据
                if (state.currentNoteDetail) {
                    state.currentNoteDetail.isLearned = result.is_learned;
                }
                showToast(result.message, 'success');
                
                // 刷新笔记列表（如果当前有筛选）
                if (state.filterLearning !== 'all') {
                    loadNotes();
                }
            } catch (error) {
                showToast(error.message || '操作失败', 'error');
            }
        });
    }
    
    // 星标切换按钮
    const starBtn = document.getElementById('detail-star-btn');
    if (starBtn) {
        starBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const noteId = starBtn.dataset.noteId;
            if (!noteId) return;
            
            try {
                const result = await api.toggleStarredStatus(noteId);
                // 更新按钮状态
                if (result.is_starred) {
                    starBtn.classList.add('starred');
                } else {
                    starBtn.classList.remove('starred');
                }
                // 更新详情数据
                if (state.currentNoteDetail) {
                    state.currentNoteDetail.isStarred = result.is_starred;
                }
                showToast(result.message, 'success');
                
                // 刷新笔记列表（如果当前在星标页面）
                if (state.currentAlbum === '星标') {
                    loadNotes();
                }
                
                // 刷新专辑列表以更新星标数量
                const albums = await api.getAlbums();
                renderAlbums(albums);
            } catch (error) {
                showToast(error.message || '操作失败', 'error');
            }
        });
    }

    // 加载更多
    if (elements.loadMoreBtn) {
        elements.loadMoreBtn.addEventListener('click', () => {
            state.currentPage++;
            loadNotes(true);
        });
    }

    // 弹窗关闭
    if (elements.modalClose) {
        elements.modalClose.addEventListener('click', closeModal);
    }
    if (elements.modalOverlay) {
        elements.modalOverlay.addEventListener('click', (e) => {
            if (e.target === elements.modalOverlay) {
                closeModal();
            }
        });
    }

    // 媒体导航
    if (elements.mediaPrev) {
        elements.mediaPrev.addEventListener('click', () => {
            if (state.mediaIndex > 0) {
                state.mediaIndex--;
                renderMedia();
            }
        });
    }

    if (elements.mediaNext) {
        elements.mediaNext.addEventListener('click', () => {
            const detail = state.currentNoteDetail;
            if (!detail) return;
            const totalMedia = (detail.images?.length || 0) + (detail.video ? 1 : 0);
            if (state.mediaIndex < totalMedia - 1) {
                state.mediaIndex++;
                renderMedia();
            }
        });
    }
    
    
    // 沉浸式查看按钮事件（使用事件委托，在弹窗打开时动态处理）
    // 不在初始化时绑定，避免元素不存在的问题
    
    // 视图切换
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => setViewMode(btn.dataset.view));
    });
    
    // 新建专辑
    const createAlbumBtn = document.getElementById('create-album-btn');
    if (createAlbumBtn) {
        createAlbumBtn.addEventListener('click', openCreateAlbumModal);
    }
    
    const createAlbumClose = document.getElementById('create-album-close');
    const createAlbumCancel = document.getElementById('create-album-cancel');
    const createAlbumSubmit = document.getElementById('create-album-submit');
    
    if (createAlbumClose) {
        createAlbumClose.addEventListener('click', closeCreateAlbumModal);
    }
    if (createAlbumCancel) {
        createAlbumCancel.addEventListener('click', closeCreateAlbumModal);
    }
    if (createAlbumSubmit) {
        createAlbumSubmit.addEventListener('click', createAlbum);
    }
    
    // 新建专辑输入框回车提交
    const albumNameInput = document.getElementById('album-name-input');
    if (albumNameInput) {
        albumNameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                createAlbum();
            }
        });
    }
    
    // 选择专辑弹窗
    const selectAlbumClose = document.getElementById('select-album-close');
    const selectAlbumCancel = document.getElementById('select-album-cancel');
    
    if (selectAlbumClose) {
        selectAlbumClose.addEventListener('click', closeAlbumSelector);
    }
    if (selectAlbumCancel) {
        selectAlbumCancel.addEventListener('click', closeAlbumSelector);
    }
    
    // 点击弹窗外部关闭
    const createAlbumModal = document.getElementById('create-album-modal');
    const selectAlbumModal = document.getElementById('select-album-modal');
    
    if (createAlbumModal) {
        createAlbumModal.addEventListener('click', (e) => {
            if (e.target === createAlbumModal) {
                closeCreateAlbumModal();
            }
        });
    }
    
    if (selectAlbumModal) {
        selectAlbumModal.addEventListener('click', (e) => {
            if (e.target === selectAlbumModal) {
                closeAlbumSelector();
            }
        });
    }

    // 键盘事件
    document.addEventListener('keydown', (e) => {
        if (!elements.modalOverlay.classList.contains('active')) return;
        
        if (e.key === 'Escape') {
            closeModal();
        } else if (e.key === 'ArrowLeft') {
            elements.mediaPrev.click();
        } else if (e.key === 'ArrowRight') {
            elements.mediaNext.click();
        }
    });
    
    // 定时刷新统计
    setInterval(renderStats, 30000);
}

// 启动应用
document.addEventListener('DOMContentLoaded', init);

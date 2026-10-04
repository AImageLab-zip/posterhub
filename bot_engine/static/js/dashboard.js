const F = {
    status: '',
    category: '',
    subfield: [],
    has_github: '',
    has_paper: '',
    favorites: '',
    mine: '',
    search: '',
    author: '',
    summary: '',
    conference: [],
    group: '',
    date_from: '',
    date_to: '',
    year_from: '',
    year_to: '',
    sort: 'date',
    order: 'desc',
    page: 1,
    per_page: 15,
};

function initFilterState() {
    const d = document.getElementById('dashboardData');
    if (!d) return;

    F.status     = d.dataset.statusFilter    || '';
    F.category   = d.dataset.categoryFilter  || '';
    F.has_github = d.dataset.hasGithubFilter || '';
    F.has_paper  = d.dataset.hasPaperFilter  || '';
    F.favorites  = d.dataset.favoritesFilter || '';
    F.mine       = d.dataset.mineFilter      || '';
    F.search     = d.dataset.searchQuery     || '';
    F.author     = d.dataset.authorFilter    || '';
    F.summary    = d.dataset.summaryFilter   || '';
    F.date_from  = d.dataset.dateFromFilter  || '';
    F.date_to    = d.dataset.dateToFilter    || '';
    F.year_from  = d.dataset.yearFromFilter  || '';
    F.year_to    = d.dataset.yearToFilter    || '';
    const cf = d.dataset.conferenceFilter || '';
    F.conference = cf ? cf.split(',').map(s => s.trim()).filter(Boolean) : [];
    F.group      = d.dataset.groupFilter     || '';
    F.sort       = d.dataset.sortBy          || 'date';
    F.order      = d.dataset.sortOrder       || 'desc';
    F.per_page   = parseInt(d.dataset.perPage, 10)      || 15;
    F.page       = parseInt(d.dataset.currentPage, 10)  || 1;

    const sf = d.dataset.subfieldFilter || '';
    F.subfield = sf ? sf.split(',').map(s => s.trim()).filter(Boolean) : [];
}

function updateExportLinks() {
    const qs = buildQueryString();
    document.querySelectorAll('.export-btn').forEach(a => {
        const base = a.getAttribute('href');
        if (!base) return;
        const path = base.split('?')[0];
        a.setAttribute('href', qs ? path + '?' + qs : path);
    });
}

function buildQueryString() {
    const p = new URLSearchParams();

    if (F.status)    p.set('status',    F.status);
    if (F.category)  p.set('category',  F.category);
    F.subfield.forEach(s => p.append('subfield', s));
    if (F.has_github) p.set('has_github', '1');
    if (F.has_paper)  p.set('has_paper',  '1');
    if (F.favorites)  p.set('favorites',  '1');
    if (F.mine)       p.set('mine',       '1');
    if (F.search)    p.set('search',    F.search);
    if (F.author)    p.set('author',    F.author);
    if (F.summary)   p.set('summary',   F.summary);
    if (F.date_from)  p.set('date_from',  F.date_from);
    if (F.date_to)    p.set('date_to',    F.date_to);
    if (F.year_from)   p.set('year_from',   F.year_from);
    if (F.year_to)     p.set('year_to',     F.year_to);
    F.conference.forEach(c => p.append('conference', c));
    if (F.group)       p.set('group',       F.group);
    if (F.sort)        p.set('sort',        F.sort);
    if (F.order)     p.set('order',     F.order);
    if (F.page > 1)  p.set('page',      F.page);
    if (F.per_page && F.per_page !== 15) p.set('per_page', String(F.per_page));

    return p.toString();
}


let _fetchController   = null;
let _isApplyingFilters = false;

function applyFilters(options = {}) {
    const {
        pushHistory       = true,
        showLoading       = true,
        clearBulkSelection = true,
    } = options;

    if (_fetchController) _fetchController.abort();
    _fetchController   = new AbortController();
    _isApplyingFilters = true;

    const qs  = buildQueryString();
    const url = window.location.pathname + (qs ? '?' + qs : '');

    if (pushHistory) history.pushState(null, '', url);

    const table = document.getElementById('tableContainer');
    if (table && showLoading) {
        table.style.opacity = '0.5';
        table.style.position = 'relative';
        let spinner = document.getElementById('_tableSpinner');
        if (!spinner) {
            spinner = document.createElement('div');
            spinner.id = '_tableSpinner';
            spinner.style.cssText = 'position:absolute;top:80px;left:50%;transform:translateX(-50%);z-index:10;background:var(--bg-surface);border:1px solid var(--border);border-radius:10px;padding:10px 22px;font-size:0.88em;color:var(--text-muted);box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;align-items:center;gap:8px;';
            spinner.innerHTML = '<span style="display:inline-block;width:16px;height:16px;border:2px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:_spin .6s linear infinite"></span> Loading...';
            table.appendChild(spinner);
        }
    }

    const ajaxUrl = window.location.pathname + (qs ? '?' + qs + '&_ajax=1' : '?_ajax=1');

    fetch(ajaxUrl, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: _fetchController.signal,
    })
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            const sp = document.getElementById('_tableSpinner');
            if (sp) sp.remove();
            if (table) {
                table.innerHTML    = data.table_html      || '';
                table.style.opacity = '1';
            }

            const pag = document.getElementById('paginationContainer');
            if (pag) pag.innerHTML = data.pagination_html || '';

            updateStats(data.stats);
            syncFilterButtons();
            rebuildSubfieldDropdown(
                data.category_filter,
                data.subfields_for_cat || [],
                data.subfield_filter   || []
            );

            if (clearBulkSelection) clearSelection();
            updateBackToTopVisibility();
            updateExportLinks();
            _syncAdvancedBadge();
        })
        .catch(err => {
            if (err.name === 'AbortError') return;
            const sp = document.getElementById('_tableSpinner');
            if (sp) sp.remove();
            console.error('Filter fetch error:', err);
            if (table) table.style.opacity = '1';
            showToast('Error loading data', 'error');
        })
        .finally(() => {
            _isApplyingFilters = false;
        });
}

window.addEventListener('pageshow', (e) => {
    if (e.persisted) applyFilters({ pushHistory: false, showLoading: false });
});
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && document.getElementById('dashboardData')) {
        applyFilters({ pushHistory: false, showLoading: false });
    }
});

window.addEventListener('popstate', () => {
    const p = new URLSearchParams(window.location.search);

    F.status    = p.get('status')    || '';
    F.category  = p.get('category')  || '';
    F.subfield  = p.getAll('subfield');
    F.has_github = p.get('has_github') || '';
    F.has_paper  = p.get('has_paper')  || '';
    F.favorites  = p.get('favorites')  || '';
    F.mine       = p.get('mine')       || '';
    F.search    = p.get('search')    || '';
    F.author    = p.get('author')    || '';
    F.summary   = p.get('summary')   || '';
    F.date_from = p.get('date_from') || '';
    F.date_to   = p.get('date_to')   || '';
    F.year_from   = p.get('year_from')   || '';
    F.year_to     = p.get('year_to')     || '';
    F.conference  = p.getAll('conference');
    F.group       = p.get('group')       || '';
    F.sort        = p.get('sort')        || 'date';
    F.order     = p.get('order')     || 'desc';
    F.page      = parseInt(p.get('page'),     10) || 1;
    F.per_page  = parseInt(p.get('per_page'), 10) || 15;

    const fields = {
        searchInput:      'search',
        filterAuthor:     'author',
        filterSummary:    'summary',
        filterDateFrom:   'date_from',
        filterDateTo:     'date_to',
        filterYearFrom:   'year_from',
        filterYearTo:     'year_to',
    };

    Object.entries(fields).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (el) el.value = F[key];
    });

    applyFilters({ pushHistory: false });
});


function syncFilterButtons() {
    document.querySelectorAll('#statusButtons .filter-btn').forEach(btn => {
        const text = btn.textContent.trim().toLowerCase();
        let match = false;

        if (!F.status && text === 'all')                         match = true;
        else if (F.status === 'pending'  && text.includes('pending'))  match = true;
        else if (F.status === 'approved' && text.includes('approved')) match = true;
        else if (F.status === 'rejected' && text.includes('rejected')) match = true;

        btn.classList.toggle('active', match);
    });

    document.querySelectorAll('#linksButtons .filter-btn').forEach(btn => {
        const text = btn.textContent.trim().toLowerCase();
        let match = false;

        if (text === 'all' && !F.has_github && !F.has_paper && !F.favorites) match = true;
        if (text.includes('github')     && F.has_github)  match = true;
        if (text.includes('paper')       && F.has_paper)   match = true;
        if (text.includes('starred')    && F.favorites)   match = true;

        btn.classList.toggle('active', match);
    });

    document.querySelectorAll('#categoryButtons .filter-btn').forEach(btn => {
        const onclick = btn.getAttribute('onclick') || '';
        const m = onclick.match(/setFilter\('category','([^']*)'\)/);
        if (m) btn.classList.toggle('active', m[1] === F.category);
    });

    document.querySelectorAll('#groupButtons .filter-btn').forEach(btn => {
        const onclick = btn.getAttribute('onclick') || '';
        const m = onclick.match(/setFilter\('group','([^']*)'\)/);
        if (m) {
            btn.classList.toggle('active', m[1] === F.group);
        } else if (onclick.includes("toggleFilter('mine'")) {
            btn.classList.toggle('active', !!F.mine);
        }
    });

    document.querySelectorAll('#conferenceButtons .filter-btn').forEach(btn => {
        const conf = btn.dataset.conf || '';
        const isAll = conf === '';
        btn.classList.toggle('active', isAll ? F.conference.length === 0 : F.conference.includes(conf));
    });

    const favCard = document.getElementById('stat-favorites-card');
    if (favCard) favCard.classList.toggle('stat-favorites-active', !!F.favorites);
}

function setFilter(key, value) {
    F[key]  = value;
    F.page  = 1;
    if (key === 'category') F.subfield = [];
    applyFilters();
}

function toggleConference(value) {
    if (!value) return;
    const i = F.conference.indexOf(value);
    if (i === -1) F.conference.push(value);
    else          F.conference.splice(i, 1);
    F.page = 1;
    applyFilters();
}

function clearConferences() {
    F.conference = [];
    F.page = 1;
    applyFilters();
}

function toggleFilter(key, value) {
    F[key] = F[key] === value ? '' : value;
    F.page = 1;
    applyFilters();
}

function clearLinksFilters() {
    F.has_github = '';
    F.has_paper  = '';
    F.favorites  = '';
    F.page       = 1;
    applyFilters();
}

function clearAllFilters() {
    Object.assign(F, {
        status: '', category: '', subfield: [],
        has_github: '', has_paper: '', favorites: '', mine: '',
        search: '', author: '', summary: '', conference: [],
        group: '',
        date_from: '', date_to: '',
        year_from: '', year_to: '',
        sort: 'date', order: 'desc', page: 1,
    });

    ['searchInput', 'filterAuthor', 'filterSummary', 'filterDateFrom', 'filterDateTo', 'filterYearFrom', 'filterYearTo']
        .forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });

    applyFilters();
}

function handleSearchSubmit(e) {
    e.preventDefault();
    const si = document.getElementById('searchInput');
    F.search = si ? si.value.trim() : '';
    F.page   = 1;
    applyFilters();
    _syncSearchClear();
    return false;
}

function clearSearch() {
    const si = document.getElementById('searchInput');
    if (si) si.value = '';
    F.search = '';
    F.page = 1;
    applyFilters();
    _syncSearchClear();
}

function _syncSearchClear() {
    const si  = document.getElementById('searchInput');
    const btn = document.getElementById('searchClearBtn');
    if (si && btn) btn.style.display = si.value.trim() ? '' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    const si = document.getElementById('searchInput');
    if (si) {
        si.addEventListener('input', _syncSearchClear);
        _syncSearchClear();
    }
});

function applyAdvancedFilters() {
    const get = id => { const el = document.getElementById(id); return el ? el.value.trim() : ''; };

    F.author     = get('filterAuthor');
    F.summary    = get('filterSummary');
    F.date_from  = get('filterDateFrom');
    F.date_to    = get('filterDateTo');
    F.year_from  = get('filterYearFrom');
    F.year_to    = get('filterYearTo');
    F.page       = 1;

    applyFilters();
}

document.addEventListener('DOMContentLoaded', () => {
    ['filterAuthor', 'filterSummary', 'filterDateFrom', 'filterDateTo', 'filterYearFrom', 'filterYearTo'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); applyAdvancedFilters(); } });
    });
});

function _syncAdvancedBadge() {
    const btn = document.querySelector('.advanced-toggle-btn');
    if (!btn) return;
    let count = 0;
    if (F.author && F.author.trim())           count++;
    if (F.summary && F.summary.trim())         count++;
    if (F.date_from && F.date_from.trim())     count++;
    if (F.date_to && F.date_to.trim())         count++;
    if (F.year_from && F.year_from.trim())     count++;
    if (F.year_to && F.year_to.trim())         count++;

    let badge = document.getElementById('advancedFilterBadge');
    if (count > 0) {
        if (!badge) {
            badge = document.createElement('span');
            badge.id = 'advancedFilterBadge';
            badge.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;border-radius:50%;background:var(--primary);color:white;font-size:0.7em;font-weight:700;line-height:1;padding:0 4px;margin-left:6px;';
            btn.appendChild(badge);
        }
        badge.textContent = String(count);
    } else if (badge) {
        badge.remove();
    }
}

function sortColumn(field) {
    if (F.sort === field) {
        F.order = F.order === 'asc' ? 'desc' : 'asc';
    } else {
        F.sort  = field;
        F.order = field === 'title' ? 'asc' : 'desc';
    }
    F.page = 1;
    applyFilters();
}

function goToPage(num)      { F.page = num; applyFilters(); }
function changePerPage(val) { F.per_page = parseInt(val, 10); F.page = 1; applyFilters(); }

function rebuildSubfieldDropdown(catFilter, subfieldsForCat, activeSubfields) {
    const wrap   = document.getElementById('subfieldDropdownWrap');
    const groups = document.getElementById('subfieldDropdownGroups');
    const tags   = document.getElementById('activeSubfieldTags');

    if (!wrap || !groups || !tags) return;

    if (!catFilter || !subfieldsForCat || subfieldsForCat.length === 0) {
        wrap.style.display = 'none';
        tags.innerHTML     = '';
        const btn = document.getElementById('subfieldBtnLabel');
        if (btn) btn.textContent = 'Filter by subfield…';
        return;
    }

    wrap.style.display = '';

    groups.innerHTML = '';
    const groupDiv = document.createElement('div');
    groupDiv.className = 'subfield-dd-group';
    subfieldsForCat.forEach(sf => {
        const label = document.createElement('label');
        label.className = 'subfield-dd-option';
        label.dataset.slug  = sf.value;
        label.dataset.label = sf.label.toLowerCase();
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = sf.value;
        cb.checked = activeSubfields.includes(sf.value);
        cb.addEventListener('change', applySubfieldFilter);
        label.appendChild(cb);
        label.appendChild(document.createTextNode(' ' + sf.label));
        groupDiv.appendChild(label);
    });
    groups.appendChild(groupDiv);

    const btn   = document.getElementById('subfieldBtnLabel');
    const count = activeSubfields.length;
    if (btn) btn.textContent = count ? `${count} subfield${count > 1 ? 's' : ''} selected` : 'Filter by subfield…';

    tags.innerHTML = '';
    activeSubfields.forEach(sf => {
        const span = document.createElement('span');
        span.className = 'subfield-active-tag';
        span.textContent = sf + ' ';
        const removeBtn = document.createElement('button');
        removeBtn.className = 'subfield-tag-remove';
        removeBtn.textContent = '\u00D7';
        removeBtn.addEventListener('click', () => removeSubfield(sf));
        span.appendChild(removeBtn);
        tags.appendChild(span);
    });
}

function toggleSubfieldDropdown() {
    const panel = document.getElementById('subfieldDropdownPanel');
    if (!panel) return;
    panel.style.display = panel.style.display !== 'none' ? 'none' : 'block';
}

document.addEventListener('click', e => {
    const wrap  = document.querySelector('.subfield-dropdown-wrap');
    const panel = document.getElementById('subfieldDropdownPanel');
    if (wrap && panel && !wrap.contains(e.target)) panel.style.display = 'none';
});

function filterSubfieldOptions(query) {
    const q = query.toLowerCase().trim();

    document.querySelectorAll('.subfield-dd-option').forEach(opt => {
        const match = !q || (opt.dataset.label || '').includes(q) || (opt.dataset.slug || '').includes(q);
        opt.style.display = match ? '' : 'none';
        opt.classList.toggle('dd-hidden', !match);
    });

    document.querySelectorAll('.subfield-dd-group').forEach(group => {
        const visible = group.querySelectorAll('.subfield-dd-option:not(.dd-hidden)');
        group.style.display = visible.length ? '' : 'none';
    });
}

function applySubfieldFilter() {
    const checked = document.querySelectorAll('#subfieldDropdownPanel input[type="checkbox"]:checked');
    F.subfield = Array.from(checked).map(cb => cb.value);
    F.page     = 1;
    applyFilters();
}

function clearSubfieldFilter() { F.subfield = []; F.page = 1; applyFilters(); }

function removeSubfield(slug) {
    F.subfield = F.subfield.filter(s => s !== slug);
    F.page     = 1;
    applyFilters();
}


function animateValue(el, start, end, duration) {
    if (start === end) { el.textContent = end; return; }

    const range     = end - start;
    const startTime = performance.now();

    function step(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const eased    = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + range * eased);
        if (progress < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
}

function updateDonut(pending, approved, rejected) {
    var total = pending + approved + rejected;
    var pPct = total ? (pending  / total) * 100 : 0;
    var aPct = total ? (approved / total) * 100 : 0;
    var rPct = total ? (rejected / total) * 100 : 0;

    var gap = 1.5;
    var segments = [[pPct, 'donut-pending'], [aPct, 'donut-approved'], [rPct, 'donut-rejected']];
    var active   = segments.filter(function (s) { return s[0] > 0; });

    if (active.length === 0) {
        segments.forEach(function (s) {
            var el = document.getElementById(s[1]);
            if (el) { el.setAttribute('stroke-dasharray', '0 100'); el.setAttribute('stroke-dashoffset', '0'); }
        });
        return;
    }

    var totalGap = active.length > 1 ? active.length * gap : 0;
    var scale    = active.length > 1 ? (100 - totalGap) / 100 : 1;
    var offset   = 0;

    segments.forEach(function (s) {
        var el = document.getElementById(s[1]);
        if (!el) return;
        var pct = s[0] * scale;
        if (pct > 0) {
            el.setAttribute('stroke-dasharray', pct + ' ' + (100 - pct));
            el.setAttribute('stroke-dashoffset', '' + (-offset));
            offset += pct + gap;
        } else {
            el.setAttribute('stroke-dasharray', '0 100');
            el.setAttribute('stroke-dashoffset', '0');
        }
    });
}

function updateStats(stats) {
    if (!stats) return;

    var map = {
        'stat-total':     stats.total     || 0,
        'stat-pending':   stats.pending   || 0,
        'stat-approved':  stats.approved  || 0,
        'stat-rejected':  stats.rejected  || 0,
        'stat-favorites': stats.favorites || 0,
    };

    Object.entries(map).forEach(function (entry) {
        var el = document.getElementById(entry[0]);
        if (el) animateValue(el, parseInt(el.textContent, 10) || 0, entry[1], 400);
    });

    updateDonut(stats.pending || 0, stats.approved || 0, stats.rejected || 0);
}


function addActivity(activity) {
    if (!activity) return;

    const list = document.getElementById('activityList');
    if (!list) return;

    const placeholder = list.querySelector('.text-muted');
    if (placeholder) placeholder.remove();

    const item = document.createElement('div');
    item.className = 'activity-item';
    item.style.cssText = 'opacity:0;transform:translateY(-10px)';

    const actionDiv = document.createElement('div');
    actionDiv.className = 'activity-action';
    actionDiv.textContent = (activity.icon || '') + ' ';
    const strong = document.createElement('strong');
    strong.textContent = activity.action_display || '';
    actionDiv.appendChild(strong);

    const detailsDiv = document.createElement('div');
    detailsDiv.className = 'activity-details';
    detailsDiv.textContent = activity.poster_title || '';

    const timeDiv = document.createElement('div');
    timeDiv.className = 'activity-time';
    timeDiv.textContent = activity.time || '';

    item.appendChild(actionDiv);
    item.appendChild(detailsDiv);
    item.appendChild(timeDiv);

    list.prepend(item);

    requestAnimationFrame(() => {
        item.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        item.style.opacity    = '1';
        item.style.transform  = 'translateY(0)';
    });

    while (list.children.length > 5) list.removeChild(list.lastChild);

    const clearBtn = document.querySelector('.clear-activity-btn');
    if (clearBtn) clearBtn.style.display = '';
}


function _createBanner(text) {
    if (!document.getElementById('_live-spin-style')) {
        const style = document.createElement('style');
        style.id    = '_live-spin-style';
        style.textContent = '@keyframes _spin { to { transform: rotate(360deg); } }';
        document.head.appendChild(style);
    }

    const el = document.createElement('div');
    el.style.cssText = [
        'position:fixed', 'top:16px', 'right:16px', 'z-index:9999',
        'background:var(--primary)', 'color:white',
        'padding:12px 20px', 'border-radius:10px',
        'font-size:14px', 'box-shadow:0 4px 12px rgba(0,0,0,.25)',
        'display:flex', 'align-items:center', 'gap:10px',
        'transition:opacity .3s ease',
    ].join(';');

    el.innerHTML = `
        <span style="display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:white;border-radius:50%;animation:_spin .8s linear infinite"></span>
        <span>${text || 'AI analysis\u2026'}</span>
    `;

    return el;
}

function _removeBanner(el) {
    if (!el) return;
    el.style.opacity = '0';
    setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 350);
}


function pollTask(taskId, { onSuccess, onFailure, onTimeout } = {}) {
    let attempts = 0;
    const MAX    = 90;

    const timer = setInterval(async () => {
        if (++attempts > MAX) {
            clearInterval(timer);
            if (onTimeout) onTimeout();
            return;
        }

        let data;
        try {
            const res = await fetch(`/task-status/${taskId}/`, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            data = await res.json();
        } catch (_) { return; }

        if (data.state === 'SUCCESS') {
            clearInterval(timer);
            if (onSuccess) onSuccess(data);
        } else if (data.state === 'FAILURE') {
            clearInterval(timer);
            if (onFailure) onFailure(data);
        }
    }, 2000);

    return { stop: () => clearInterval(timer) };
}


let _liveLatestId      = 0;
let _liveProcessing    = 0;
let _liveBaselineReady = false;
let _liveTimer         = null;
let _liveBanner        = null;
let _liveSuppressed    = false;

function _showLiveBanner() { if (_liveBanner || _liveSuppressed) return; _liveBanner = _createBanner(); document.body.appendChild(_liveBanner); }
function _hideLiveBanner()  { if (!_liveBanner) return; _removeBanner(_liveBanner); _liveBanner = null; }

async function checkLiveStatus() {
    try {
        const res = await fetch('/dashboard/live-status/', {
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            redirect: 'manual',
        });

        if (res.type === 'opaqueredirect' || res.status === 0
            || res.status === 401 || res.status === 302) {
            stopLivePolling();
            return;
        }

        if (!res.ok) return;

        const ct = res.headers.get('content-type') || '';
        if (!ct.includes('application/json')) {
            stopLivePolling();
            return;
        }

        const data          = await res.json();
        const newProcessing = data.processing || 0;
        const newLatestId   = data.latest_id  || 0;

        if (!_liveBaselineReady) {
            _liveBaselineReady = true;
            _liveLatestId      = newLatestId;
            _liveProcessing    = newProcessing;
            if (newProcessing > 0) _showLiveBanner();
            return;
        }

        const hasNew       = newLatestId   > _liveLatestId;
        const statusChanged = newProcessing !== _liveProcessing;

        if (newProcessing > 0 && _liveProcessing === 0) _showLiveBanner();
        if (newProcessing === 0 && _liveProcessing > 0) _hideLiveBanner();

        _liveLatestId   = newLatestId;
        _liveProcessing = newProcessing;

        if (hasNew) F.page = 1;

        if (hasNew || statusChanged) {
            applyFilters({ pushHistory: false, showLoading: false, clearBulkSelection: false });
        }
    } catch (e) {
        stopLivePolling();
    }
}

function startLivePolling() {
    if (_liveTimer) return;
    checkLiveStatus();
    _liveTimer = setInterval(checkLiveStatus, 3000);
}

function stopLivePolling() {
    if (_liveTimer) { clearInterval(_liveTimer); _liveTimer = null; }
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopLivePolling();
    } else {
        _liveBaselineReady = false;
        _liveLatestId      = 0;
        _liveProcessing    = 0;
        startLivePolling();
    }
});

function retryAnalysis(posterId, button) {
    const originalHTML = button.innerHTML;
    button.disabled    = true;
    button.innerHTML   = '⏳';

    fetch(`/retry-analysis/${posterId}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
        },
    })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                button.disabled  = false;
                button.innerHTML = originalHTML;
                showToast(data.error || 'Retry failed', 'error');
                return;
            }

            _liveSuppressed = true;
            _hideLiveBanner();
            const banner = _createBanner('Retry analysis\u2026');
            document.body.appendChild(banner);
            applyFilters({ pushHistory: false });

            const warningMsgs = {
                no_text:         ['⚠️ No scientific content detected',          'error'],
                rejected:        ['⚠️ No scientific content detected',          'error'],
                duplicate:       ['⚠️ Duplicate — already in collection',       'info'],
                analysis_failed: ['❌ Analysis failed again — check connection', 'error'],
            };

            function _retryDone() {
                _removeBanner(banner);
                _liveSuppressed = false;
                _hideLiveBanner();
                _liveBaselineReady = false;
                setTimeout(() => applyFilters({ pushHistory: false }), 600);
            }

            pollTask(data.task_id, {
                onSuccess: result => {
                    _retryDone();
                    const key = result.warning || result.status;
                    if (key && warningMsgs[key]) {
                        const [msg, type] = warningMsgs[key];
                        showToast(msg, type);
                    } else {
                        showToast(`✅ "${result.title || 'Paper'}" analysed!`);
                    }
                },
                onFailure: result => {
                    _retryDone();
                    showToast('❌ Retry failed: ' + (result?.error || 'unknown'), 'error');
                },
                onTimeout: () => {
                    _retryDone();
                    showToast('⚠️ Analysis timeout', 'error');
                },
            });
        })
        .catch(() => {
            button.disabled  = false;
            button.innerHTML = originalHTML;
            showToast('Network error', 'error');
        });
}

function stopAnalysis(posterId, button) {
    button.disabled = true;

    fetch(`/stop-analysis/${posterId}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
        },
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('⏹ Analysis stopped', 'info');
                setTimeout(() => applyFilters({ pushHistory: false }), 500);
            } else {
                button.disabled = false;
                showToast(data.error || 'Error stopping analysis', 'error');
            }
        })
        .catch(() => { button.disabled = false; showToast('Network error', 'error'); });
}

function copyToClipboard(text, button) {
    navigator.clipboard.writeText(text).then(() => {
        const originalHTML = button.innerHTML;
        button.innerHTML   = '✓';
        button.style.cssText = 'background:#10b981;color:white;transform:scale(1.15)';

        setTimeout(() => {
            button.innerHTML   = originalHTML;
            button.style.cssText = '';
        }, 1200);
    });
}

function updateStatus(selectEl) {
    const form      = selectEl.closest('form');
    const newStatus = selectEl.value;

    fetch(form.action, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `status=${encodeURIComponent(newStatus)}`,
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                selectEl.className = `status-select status-${newStatus}`;

                const row = selectEl.closest('tr');
                if (row) {
                    const mobBadge = row.querySelector('.status-mob-badge');
                    if (mobBadge) {
                        mobBadge.className = `status-mob-badge status-${newStatus}`;
                        mobBadge.textContent = `● ${newStatus.charAt(0).toUpperCase() + newStatus.slice(1)}`;
                    }
                }
                if (row) {
                    row.classList.remove('row-approved', 'row-pending', 'row-rejected');
                    row.classList.add(`row-${newStatus}`);
                }

                showToast(data.message);
                updateStats(data.stats);
                addActivity(data.activity);
            } else {
                showToast('Error updating status', 'error');
            }
        })
        .catch(() => showToast('Network error', 'error'));
}

function toggleFavorite(posterId, button) {
    fetch(`/toggle-favorite/${posterId}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
        },
    })
        .then(res => res.json())
        .then(data => {
            if (!data.success) return;

            const filledSVG = `<svg class="btn-icon icon-star" viewBox="0 0 1024 1024" fill="currentColor"><path d="M908.1 353.1l-253.9-36.9L540.7 86.1c-3.1-6.3-8.2-11.4-14.5-14.5-15.8-7.8-35-1.3-42.9 14.5L369.8 316.2l-253.9 36.9c-7 1-13.4 4.3-18.3 9.3a32.05 32.05 0 0 0 .6 45.3l183.7 179.1-43.4 252.9a31.95 31.95 0 0 0 46.4 33.7L512 754l227.1 119.4c6.2 3.3 13.4 4.4 20.3 3.2 17.4-3 29.1-19.5 26.1-36.9l-43.4-252.9 183.7-179.1c5-4.9 8.3-11.3 9.3-18.3 2.7-17.5-9.5-33.7-27-36.3z"/></svg>`;
            const emptySVG  = `<svg class="btn-icon icon-star-empty" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.2691 4.41115C11.5006 3.89177 11.6164 3.63208 11.7776 3.55211C11.9176 3.48263 12.082 3.48263 12.222 3.55211C12.3832 3.63208 12.499 3.89177 12.7305 4.41115L14.5745 8.54808C14.643 8.70162 14.6772 8.77839 14.7302 8.83718C14.777 8.8892 14.8343 8.93081 14.8982 8.95929C14.9705 8.99149 15.0541 9.00031 15.2213 9.01795L19.7256 9.49336C20.2911 9.55304 20.5738 9.58288 20.6997 9.71147C20.809 9.82316 20.8598 9.97956 20.837 10.1342C20.8108 10.3122 20.5996 10.5025 20.1772 10.8832L16.8125 13.9154C16.6877 14.0279 16.6252 14.0842 16.5857 14.1527C16.5507 14.2134 16.5288 14.2807 16.5215 14.3503C16.5132 14.429 16.5306 14.5112 16.5655 14.6757L17.5053 19.1064C17.6233 19.6627 17.6823 19.9408 17.5989 20.1002C17.5264 20.2388 17.3934 20.3354 17.2393 20.3615C17.0619 20.3915 16.8156 20.2495 16.323 19.9654L12.3995 17.7024C12.2539 17.6184 12.1811 17.5765 12.1037 17.56C12.0352 17.5455 11.9644 17.5455 11.8959 17.56C11.8185 17.5765 11.7457 17.6184 11.6001 17.7024L7.67662 19.9654C7.18404 20.2495 6.93775 20.3915 6.76034 20.3615C6.60623 20.3354 6.47319 20.2388 6.40075 20.1002C6.31736 19.9408 6.37635 19.6627 6.49434 19.1064L7.4341 14.6757C7.46898 14.5112 7.48642 14.429 7.47814 14.3503C7.47081 14.2807 7.44894 14.2134 7.41394 14.1527C7.37439 14.0842 7.31195 14.0279 7.18708 13.9154L3.82246 10.8832C3.40005 10.5025 3.18884 10.3122 3.16258 10.1342C3.13978 9.97956 3.19059 9.82316 3.29993 9.71147C3.42581 9.58288 3.70856 9.55304 4.27406 9.49336L8.77835 9.01795C8.94553 9.00031 9.02911 8.99149 9.10139 8.95929C9.16534 8.93081 9.2226 8.8892 9.26946 8.83718C9.32241 8.77839 9.35663 8.70162 9.42508 8.54808L11.2691 4.41115Z"/></svg>`;

            button.innerHTML = data.is_favorite ? filledSVG : emptySVG;
            button.classList.toggle('favorited', data.is_favorite);
            button.title = data.is_favorite ? 'Remove from favorites' : 'Add to favorites';


            const row    = button.closest('tr');
            const idCell = row ? row.querySelector('td:nth-child(2)') : null;
            const indicators = idCell ? idCell.querySelector('.id-cell-indicators') : null;
            let starEl = indicators ? indicators.querySelector('.id-cell-icon.icon-star') : null;

            if (data.is_favorite) {
                if (indicators && !starEl) {
                    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                    svg.setAttribute('class', 'id-cell-icon icon-star');
                    svg.setAttribute('viewBox', '0 0 1024 1024');
                    svg.setAttribute('fill', 'currentColor');
                    svg.innerHTML = '<path d="M908.1 353.1l-253.9-36.9L540.7 86.1c-3.1-6.3-8.2-11.4-14.5-14.5-15.8-7.8-35-1.3-42.9 14.5L369.8 316.2l-253.9 36.9c-7 1-13.4 4.3-18.3 9.3a32.05 32.05 0 0 0 .6 45.3l183.7 179.1-43.4 252.9a31.95 31.95 0 0 0 46.4 33.7L512 754l227.1 119.4c6.2 3.3 13.4 4.4 20.3 3.2 17.4-3 29.1-19.5 26.1-36.9l-43.4-252.9 183.7-179.1c5-4.9 8.3-11.3 9.3-18.3 2.7-17.5-9.5-33.7-27-36.3z"/>';
                    indicators.appendChild(svg);
                } else if (!indicators && idCell) {
                    const div = document.createElement('div');
                    div.className = 'id-cell-indicators';
                    div.innerHTML = `<svg class="id-cell-icon icon-star" viewBox="0 0 1024 1024" fill="currentColor"><path d="M908.1 353.1l-253.9-36.9L540.7 86.1c-3.1-6.3-8.2-11.4-14.5-14.5-15.8-7.8-35-1.3-42.9 14.5L369.8 316.2l-253.9 36.9c-7 1-13.4 4.3-18.3 9.3a32.05 32.05 0 0 0 .6 45.3l183.7 179.1-43.4 252.9a31.95 31.95 0 0 0 46.4 33.7L512 754l227.1 119.4c6.2 3.3 13.4 4.4 20.3 3.2 17.4-3 29.1-19.5 26.1-36.9l-43.4-252.9 183.7-179.1c5-4.9 8.3-11.3 9.3-18.3 2.7-17.5-9.5-33.7-27-36.3z"/></svg>`;
                    const idCellDiv = idCell.querySelector('.id-cell');
                    if (idCellDiv) idCellDiv.appendChild(div);
                }
            } else if (starEl) {
                starEl.remove();
                if (indicators && indicators.children.length === 0)
                    indicators.remove();
            }

            updateStats(data.stats);
            addActivity(data.activity);
        })
        .catch(() => showToast('Network error', 'error'));
}

function confirmDelete(posterId, posterTitle) {
    openPosterDeleteModal(posterId, posterTitle, onPosterDeleteDone);
}

function onPosterDeleteDone(kind, data, posterId) {
    if (!data.success) {
        showToast(data.error || (kind === 'remove' ? 'Error removing paper' : 'Error deleting paper'), 'error');
        return;
    }

    if (kind === 'remove') {
        // The paper may still be visible (other groups of the caller, or uploader): just reload the table.
        applyFilters({ pushHistory: false });
    } else {
        const row = document.querySelector(`tr[data-poster-id="${posterId}"]`);
        if (row) {
            row.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            row.style.opacity    = '0';
            row.style.transform  = 'translateX(-20px)';

            setTimeout(() => {
                row.remove();
                const tbody = document.querySelector('tbody');
                if (tbody && tbody.children.length === 0) {
                    const tc = document.getElementById('tableContainer');
                    if (tc) tc.innerHTML = `
                        <div class="empty-state">
                            <p>No research papers available</p>
                            <a href="/" class="btn">Add Your First Paper</a>
                        </div>
                    `;
                }
            }, 300);
        }
    }

    showToast(data.message);
    updateStats(data.stats);
    addActivity(data.activity);
}

function clearAllActivities() {
    var modal = document.getElementById('clearActivityModal');
    if (modal) modal.style.display = '';
}

function executeClearActivities() {
    var modal = document.getElementById('clearActivityModal');
    if (modal) modal.style.display = 'none';

    fetch('/delete-all-activities/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
        },
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const list = document.getElementById('activityList');
                if (list) list.innerHTML = '<p class="text-muted">No recent activity</p>';
                showToast(data.message);
            }
        })
        .catch(() => showToast('Network error', 'error'));
}

function toggleActivitySidebar() {
    const list   = document.getElementById('activityList');
    const btn    = document.getElementById('toggleActivityBtn');
    if (!list || !btn) return;

    const isHidden = list.style.display === 'none';
    list.style.display = isHidden ? 'flex' : 'none';
    btn.textContent    = isHidden ? '▼' : '▶';
    btn.title          = isHidden ? 'Hide activity log' : 'Show activity log';

    try { localStorage.setItem('activitySidebarHidden', String(!isHidden)); } catch (e) {}
}

function toggleText(type, posterId) {
    const btn = document.getElementById(`${type}-btn-${posterId}`);
    const box = btn && btn.closest('.expandable-text');
    if (!box) return;

    const row = box.closest('tr');
    const scrollBefore = window.scrollY;
    const rowTopBefore = row ? row.getBoundingClientRect().top : 0;

    const expand = !box.classList.contains('is-expanded');
    box.classList.toggle('is-expanded', expand);
    btn.textContent = expand ? '↑ Hide' : '↓ Read more';
    if (row) fitRowText(row);

    if (row) {
        const rowTopAfter = row.getBoundingClientRect().top;
        const drift = rowTopAfter - rowTopBefore;
        if (Math.abs(drift) > 1) {
            window.scrollTo({ top: scrollBefore + drift, behavior: 'instant' });
        }
        if (rowTopAfter < 0) {
            row.scrollIntoView({ behavior: 'instant', block: 'start' });
        }
    }
}

// While a row has user-expanded text, show in full any other truncated text in that
// row that fits in the row's current height ('is-auto', no button); fold it back
// once nothing in the row is expanded by the user.
function fitRowText(row) {
    const boxes = Array.from(row.querySelectorAll('.expandable-text'));
    boxes.filter(b => b.classList.contains('is-auto'))
         .forEach(b => b.classList.remove('is-expanded', 'is-auto'));
    if (!boxes.some(b => b.classList.contains('is-expanded'))) return;

    boxes.filter(b => !b.classList.contains('is-expanded')).forEach(b => {
        const height = row.getBoundingClientRect().height;
        b.classList.add('is-expanded', 'is-auto');
        if (row.getBoundingClientRect().height > height + 0.5) {
            b.classList.remove('is-expanded', 'is-auto');
        }
    });
}

let fitRowsTimer;
window.addEventListener('resize', () => {
    clearTimeout(fitRowsTimer);
    fitRowsTimer = setTimeout(() => {
        document.querySelectorAll('#dashboard-table tbody tr').forEach(row => {
            if (row.querySelector('.expandable-text.is-expanded')) fitRowText(row);
        });
    }, 150);
});

const backToTopBtn = document.getElementById('backToTop');

function updateBackToTopVisibility() {
    if (backToTopBtn) backToTopBtn.classList.toggle('visible', window.scrollY > 360);
}

window.addEventListener('scroll', updateBackToTopVisibility);

if (backToTopBtn) {
    backToTopBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}

function toggleAdvancedFilters() {
    const panel = document.getElementById('advancedFilters');
    const icon  = document.getElementById('advancedToggleIcon');
    if (!panel || !icon) return;

    const isOpen = panel.classList.toggle('open');
    icon.textContent = isOpen ? '▲' : '▼';
    try { localStorage.setItem('advancedFiltersOpen', String(isOpen)); } catch (e) {}
}

function toggleNotes(posterId) {
    const editor = document.getElementById(`notes-editor-${posterId}`);
    if (!editor) return;
    editor.style.display = editor.style.display === 'none' ? 'block' : 'none';
    const textarea = document.getElementById(`notes-text-${posterId}`);
    const counter = document.getElementById(`notes-counter-${posterId}`);
    if (textarea && counter) {
        counter.textContent = textarea.value.length;
        textarea.removeEventListener('input', textarea._counterFn);
        textarea._counterFn = function () {
            counter.textContent = textarea.value.length;
            counter.parentElement.classList.toggle('over-limit', textarea.value.length >= 500);
        };
        textarea.addEventListener('input', textarea._counterFn);
    }
}

function saveNotes(posterId) {
    const textarea = document.getElementById(`notes-text-${posterId}`);
    if (!textarea) return;

    const notes = textarea.value;

    fetch(`/update-notes/${posterId}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notes }),
    })
        .then(res => res.json())
        .then(data => {
            if (!data.success) { showToast('Error saving notes', 'error'); return; }

            const label = document.getElementById(`notes-label-${posterId}`);
            if (label) label.textContent = notes ? 'Edit' : 'Add comment';

            const display = document.getElementById(`notes-display-${posterId}`);
            if (display) {
                if (notes) {
                    display.textContent = '\u{1F4DD} ' + (notes.length > 120 ? notes.slice(0, 117) + '...' : notes);
                } else {
                    display.remove();
                }
            } else if (notes) {
                const container = document.getElementById(`notes-container-${posterId}`);
                const toggleBtn = container ? container.querySelector('.notes-toggle') : null;
                if (container && toggleBtn) {
                    const div = document.createElement('div');
                    div.id = `notes-display-${posterId}`;
                    div.className = 'text-muted';
                    div.style.cssText = 'font-size:0.82em; margin-top:4px;';
                    div.textContent = '\u{1F4DD} ' + (notes.length > 120 ? notes.slice(0, 117) + '...' : notes);
                    container.insertBefore(div, toggleBtn);
                }
            }

            const editor = document.getElementById(`notes-editor-${posterId}`);
            if (editor) editor.style.display = 'none';

            showToast(data.message);
        })
        .catch(() => showToast('Network error', 'error'));
}

function toggleSelectAll(masterCheckbox) {
    document.querySelectorAll('.bulk-checkbox').forEach(cb => {
        cb.checked = masterCheckbox.checked;
    });
    updateBulkBar();
}

function updateBulkBar() {
    const checked = document.querySelectorAll('.bulk-checkbox:checked');
    const total   = document.querySelectorAll('.bulk-checkbox');
    const bar     = document.getElementById('bulkBar');
    const count   = document.getElementById('bulkCount');
    const allCb   = document.getElementById('selectAll');

    if (count) count.textContent = checked.length;
    if (bar)   bar.classList.toggle('visible', checked.length > 0);

    if (allCb) {
        allCb.checked       = total.length > 0 && checked.length === total.length;
        allCb.indeterminate = checked.length > 0 && checked.length < total.length;
    }
}

function clearSelection() {
    document.querySelectorAll('.bulk-checkbox').forEach(cb => { cb.checked = false; });
    const allCb = document.getElementById('selectAll');
    if (allCb) allCb.checked = false;
    updateBulkBar();
}

function getSelectedIds() {
    return Array.from(document.querySelectorAll('.bulk-checkbox:checked'))
        .map(cb => parseInt(cb.value, 10));
}

function bulkAction(action) {
    const ids = getSelectedIds();
    if (!ids.length) return;
    if (action === 'delete') {
        const run = () => _runBulkAction(ids, action);
        if (typeof window.confirmDialog === 'function') {
            window.confirmDialog(
                'Delete papers',
                `Delete ${ids.length} paper${ids.length > 1 ? 's' : ''}? This cannot be undone. `
                + 'Papers also shared with groups you are not part of are only removed from your groups.',
                'Delete',
                run,
            );
        } else {
            run();
        }
        return;
    }
    _runBulkAction(ids, action);
}

function _runBulkAction(ids, action) {
    fetch('/bulk-action/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ids, action }),
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                updateStats(data.stats);
                applyFilters({ pushHistory: false });
                clearSelection();
            } else {
                showToast(data.error || 'Error', 'error');
            }
        })
        .catch(() => showToast('Network error', 'error'));
}


window.addEventListener('DOMContentLoaded', () => {
    initFilterState();
    _syncAdvancedBadge();
    _syncSearchClear();
    updateBackToTopVisibility();


    var ip = parseInt(document.getElementById('stat-pending')?.textContent, 10) || 0;
    var ia = parseInt(document.getElementById('stat-approved')?.textContent, 10) || 0;
    var ir = parseInt(document.getElementById('stat-rejected')?.textContent, 10) || 0;
    updateDonut(ip, ia, ir);


    document.querySelectorAll('.donut-segment').forEach(function (seg) {
        seg.addEventListener('mouseenter', function () { seg.setAttribute('stroke-width', '5.5'); });
        seg.addEventListener('mouseleave', function () { seg.setAttribute('stroke-width', '4'); });
        seg.addEventListener('click', function () {
            var id = seg.id.replace('donut-', '');
            if (id === 'pending' || id === 'approved' || id === 'rejected') toggleFilter('status', id);
        });
    });


    if (localStorage.getItem('activitySidebarHidden') === 'true') {
        const al = document.getElementById('activityList');
        const tb = document.getElementById('toggleActivityBtn');
        if (al) al.style.display = 'none';
        if (tb) { tb.textContent = '▶'; tb.title = 'Show activity log'; }
    }


    const hasAdvancedFilters = !!(F.author || F.summary || F.date_from || F.date_to || F.year_from || F.year_to);
    const wasOpen = localStorage.getItem('advancedFiltersOpen') === 'true';
    if (hasAdvancedFilters || wasOpen) {
        const af = document.getElementById('advancedFilters');
        const ai = document.getElementById('advancedToggleIcon');
        if (af) af.classList.add('open');
        if (ai) ai.textContent = '▲';
    }


    (function startUploadPolling() {
        const params = new URLSearchParams(window.location.search);
        const taskId = params.get('task_id');
        if (!taskId) return;

        params.delete('task_id');
        history.replaceState(
            null,
            '',
            window.location.pathname + (params.toString() ? '?' + params.toString() : '')
        );


        _showLiveBanner();

        const warningMsgs = {
            duplicate:       ['⚠️ Duplicate paper — already in collection',     'info'],
            no_text:         ['⚠️ No scientific content detected',              'error'],
            rejected:        ['⚠️ No scientific content detected',              'error'],
            analysis_failed: ['❌ Analysis failed — use Retry in the dashboard', 'error'],
        };

        pollTask(taskId, {
            onSuccess: data => {
                _hideLiveBanner();
                const key = data.warning || data.status;
                if (key && warningMsgs[key]) {
                    const [msg, type] = warningMsgs[key];
                    showToast(msg, type);
                } else {
                    showToast(`✅ "${data.title || 'Paper'}" analysed!`);
                }
                applyFilters({ pushHistory: false, showLoading: false, clearBulkSelection: false });
            },
            onFailure: data => {
                _hideLiveBanner();
                showToast('❌ Analysis error: ' + (data?.error || 'unknown'), 'error');
                applyFilters({ pushHistory: false, showLoading: false, clearBulkSelection: false });
            },
            onTimeout: () => {
                _hideLiveBanner();
                showToast('⚠️ Analysis timed out — please reload the page', 'error');
            },
        });
    })();

    startLivePolling();
});

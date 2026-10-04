function copyDetailLink(text) {
    navigator.clipboard.writeText(text).then(function () {
        showToast('Link copied!');
    });
}

function confirmDeleteDetail(posterId, posterTitle) {
    openPosterDeleteModal(posterId, posterTitle);
}

function retryAnalysisDetail(posterId) {
    var btn = document.getElementById('retryBtn');
    if (!btn) return;
    var original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg> Retrying…';

    fetch('/retry-analysis/' + posterId + '/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCSRFToken(), 'X-Requested-With': 'XMLHttpRequest' },
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (!data.success) {
            btn.disabled = false; btn.innerHTML = original;
            showToast(data.error || 'Retry failed', 'error'); return;
        }
        showToast('Analysis restarted…', 'info');
        var interval = setInterval(function () {
            fetch('/task-status/' + data.task_id + '/')
                .then(function (r) { return r.json(); })
                .then(function (stat) {
                    if (stat.state === 'SUCCESS') { clearInterval(interval); window.location.reload(); }
                    else if (stat.state === 'FAILURE') {
                        clearInterval(interval); btn.disabled = false; btn.innerHTML = original;
                        showToast('Analysis failed again', 'error');
                    }
                })
                .catch(function () {});
        }, 2000);
    })
    .catch(function () { btn.disabled = false; btn.innerHTML = original; showToast('Network error', 'error'); });
}

function stopAnalysisDetail(posterId) {
    var btn = document.getElementById('stopBtn');
    if (!btn) return;
    btn.disabled = true;
    fetch('/stop-analysis/' + posterId + '/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCSRFToken(), 'X-Requested-With': 'XMLHttpRequest' },
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.success) { showToast('Analysis stopped', 'info'); setTimeout(function () { window.location.reload(); }, 700); }
        else { btn.disabled = false; showToast(data.error || 'Error', 'error'); }
    })
    .catch(function () { btn.disabled = false; showToast('Network error', 'error'); });
}

(function () {
    var btn = document.getElementById('backToTop');
    if (!btn) return;
    window.addEventListener('scroll', function () {
        btn.classList.toggle('visible', window.scrollY > 360);
    });
    btn.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
})();

document.addEventListener('click', function (e) {
    var link = e.target.closest('a[data-back-to-dashboard]');
    if (!link) return;
    if (document.referrer && document.referrer.indexOf('/dashboard') !== -1) {
        e.preventDefault();
        history.back();
    }
});


(function () {
    var cfg = window.posterDetailConfig || {};

    function getCurrentTags() {
        return Array.from(document.querySelectorAll('#tagsDisplay .detail-tag-removable'))
            .map(function (el) { return el.dataset.tag; });
    }

    function renderTags(tagsList) {
        var display = document.getElementById('tagsDisplay');
        if (!display) return;
        display.innerHTML = '';
        if (tagsList && tagsList.length) {
            tagsList.forEach(function (tag) {
                var span = document.createElement('span');
                span.className = 'detail-tag-item detail-tag-removable';
                span.dataset.tag = tag;
                var removeBtn = document.createElement('button');
                removeBtn.className = 'tag-remove-btn';
                removeBtn.dataset.action = 'remove-tag';
                removeBtn.innerHTML = '&times;';
                span.appendChild(document.createTextNode(tag + ' '));
                span.appendChild(removeBtn);
                display.appendChild(span);
            });
        } else {
            var empty = document.createElement('span');
            empty.className = 'detail-section-body empty';
            empty.id = 'tagsEmpty';
            empty.textContent = 'No tags yet.';
            display.appendChild(empty);
        }
    }

    function saveTags(tagsString, customMsg, fallbackTags) {
        if (!cfg.posterId) return;
        fetch('/update-tags/' + cfg.posterId + '/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ tags: tagsString }),
        })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (res) {
            if (!res.ok || !res.data || !res.data.success) {
                showToast((res.data && res.data.message) || 'Error', 'error');
                if (fallbackTags) renderTags(fallbackTags);
                return;
            }
            renderTags(res.data.tags_list);
            showToast(customMsg || res.data.message);
        })
        .catch(function () {
            showToast('Network error', 'error');
            if (fallbackTags) renderTags(fallbackTags);
        });
    }

    function removeTag(btn) {
        var tagEl = btn.closest('.detail-tag-removable');
        if (!tagEl) return;
        var removed = tagEl.dataset.tag;
        var before = getCurrentTags();
        var remaining = before.filter(function (t) { return t !== removed; });
        renderTags(remaining);
        saveTags(remaining.join(', '), 'Tag "' + removed + '" removed', before);
    }

    function addTags() {
        var input = document.getElementById('tagEditorInput');
        if (!input || !input.value.trim()) return;
        var before = getCurrentTags();
        var existing = before.slice();
        var newTags = input.value.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
        var existingLower = existing.map(function (t) { return t.toLowerCase(); });
        newTags.forEach(function (t) {
            if (existingLower.indexOf(t.toLowerCase()) === -1) {
                existing.push(t);
                existingLower.push(t.toLowerCase());
            }
        });
        input.value = '';
        renderTags(existing);
        saveTags(existing.join(', '), null, before);
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof initTagAutocomplete === 'function') {
            initTagAutocomplete('tagEditorInput');
        }
        var addBtn = document.getElementById('addTagsBtn');
        if (addBtn) addBtn.addEventListener('click', addTags);
    });

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-action="remove-tag"]');
        if (btn) removeTag(btn);
    });
})();


(function () {
    var cfg = window.posterDetailConfig || {};
    var contentSnapshot = '';
    var cache = {};

    function renderWhyUseful(el, text, noInterests) {
        el.style.display = '';
        if (noInterests) {
            el.innerHTML = '<div class="detail-section-body empty">This group has no research interests defined — evaluation not applicable.</div>';
        } else if (text) {
            el.innerHTML = '<div class="detail-section-body">' + text.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>';
        } else {
            el.innerHTML = '<div class="detail-section-body empty">No evaluation available for this group.</div>';
        }
    }

    function loadForGroup(groupId) {
        var sel = document.getElementById('whyUsefulGroupSelect');
        var defaultGroupId = sel ? sel.getAttribute('data-default') : '';
        var resolvedId = groupId || defaultGroupId;
        var contentEl = document.getElementById('whyUsefulContent');
        var loadingEl = document.getElementById('whyUsefulLoading');
        if (!contentEl || !loadingEl) return;

        if (!resolvedId) {
            contentEl.innerHTML = contentSnapshot;
            contentEl.style.display = '';
            loadingEl.style.display = 'none';
            return;
        }
        if (cache[resolvedId] !== undefined) {
            renderWhyUseful(contentEl, cache[resolvedId], cache[resolvedId] === null);
            loadingEl.style.display = 'none';
            return;
        }
        if (!cfg.whyUsefulUrl) return;
        contentEl.style.display = 'none';
        loadingEl.style.display = '';
        fetch(cfg.whyUsefulUrl + '?group_id=' + resolvedId, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            loadingEl.style.display = 'none';
            if (data.no_interests) {
                cache[resolvedId] = null;
                renderWhyUseful(contentEl, null, true);
                return;
            }
            var text = data.why_useful || '';
            cache[resolvedId] = text;
            renderWhyUseful(contentEl, text);
        })
        .catch(function () {
            contentEl.innerHTML = '<div class="detail-section-body empty">Failed to load.</div>';
            contentEl.style.display = '';
            loadingEl.style.display = 'none';
        });
    }

    function clearCache() { cache = {}; }

    document.addEventListener('DOMContentLoaded', function () {
        var contentEl = document.getElementById('whyUsefulContent');
        contentSnapshot = contentEl ? contentEl.innerHTML : '';
        var sel = document.getElementById('whyUsefulGroupSelect');
        if (!sel) return;
        sel.addEventListener('change', function () { loadForGroup(this.value); });
        var defaultId = sel.getAttribute('data-default');
        if (defaultId) {
            var opt = sel.querySelector('option[value="' + defaultId + '"]');
            if (opt) opt.selected = true;
            loadForGroup(defaultId);
        }
    });

    window.loadWhyUsefulForGroup = loadForGroup;
    window._whyUsefulClearCache = clearCache;
})();


(function () {
    var cfg = window.posterDetailConfig || {};

    function open() {
        var panel = document.getElementById('groupsEditorPanel');
        if (panel) panel.style.display = 'block';
        var btn = document.getElementById('editGroupsBtn');
        if (btn) btn.style.display = 'none';
        var status = document.getElementById('groupsEditorStatus');
        if (status) status.textContent = '';
    }

    function close() {
        var panel = document.getElementById('groupsEditorPanel');
        if (panel) panel.style.display = 'none';
        var btn = document.getElementById('editGroupsBtn');
        if (btn) btn.style.display = '';
    }

    function refreshChips(visibleGroups) {
        var chipsRow = document.getElementById('detailGroupsChips');
        if (!chipsRow) return;
        chipsRow.innerHTML = '';
        if (!visibleGroups.length) {
            var empty = document.createElement('span');
            empty.id = 'detailGroupsEmpty';
            empty.className = 'detail-groups-empty';
            empty.textContent = 'Not assigned to any group yet.';
            chipsRow.appendChild(empty);
            return;
        }
        visibleGroups.forEach(function (g) {
            var a = document.createElement('a');
            a.href = '/dashboard/?group=' + g.id;
            a.className = 'detail-tag-item group-chip';
            a.title = 'Filter dashboard by ' + g.name;
            a.textContent = g.name;
            chipsRow.appendChild(a);
        });
    }

    function refreshWhyUsefulSelect(userGroups) {
        var sel = document.getElementById('whyUsefulGroupSelect');
        if (!sel) return;
        var currentVal = sel.value;
        var defaultId = sel.getAttribute('data-default') || '';
        sel.innerHTML = '';
        userGroups.forEach(function (g) {
            var opt = document.createElement('option');
            opt.value = g.id;
            opt.textContent = g.name;
            sel.appendChild(opt);
        });
        if (typeof window._whyUsefulClearCache === 'function') {
            window._whyUsefulClearCache();
        }
        if (!userGroups.length) return;

        var newVal;
        if (currentVal && sel.querySelector('option[value="' + currentVal + '"]')) {
            newVal = currentVal;
        } else if (defaultId && sel.querySelector('option[value="' + defaultId + '"]')) {
            newVal = defaultId;
        } else {
            newVal = String(userGroups[0].id);
        }
        sel.value = newVal;
        if (newVal !== currentVal && typeof window.loadWhyUsefulForGroup === 'function') {
            window.loadWhyUsefulForGroup(newVal);
        }
    }

    function save() {
        if (!cfg.updateGroupsUrl) return;
        var checkboxes = document.querySelectorAll('#groupsEditorChips input[type="checkbox"]');
        var ids = [];
        checkboxes.forEach(function (cb) {
            if (cb.checked) ids.push(parseInt(cb.dataset.groupId, 10));
        });

        var status = document.getElementById('groupsEditorStatus');
        if (!ids.length) {
            if (status) { status.textContent = 'Select at least one group.'; status.style.color = '#dc2626'; }
            return;
        }

        var saveBtn = document.getElementById('saveGroupsBtn');
        if (saveBtn) saveBtn.disabled = true;
        if (status) { status.textContent = 'Saving…'; status.style.color = 'var(--text-faint)'; }

        fetch(cfg.updateGroupsUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({ group_ids: ids }),
        })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
            if (saveBtn) saveBtn.disabled = false;
            if (!res.ok || !res.data || !res.data.success) {
                if (status) {
                    status.textContent = (res.data && res.data.message) || 'Failed to save.';
                    status.style.color = '#dc2626';
                }
                return;
            }
            refreshChips(res.data.user_groups || []);
            refreshWhyUsefulSelect(res.data.user_groups || []);
            if (status) { status.textContent = 'Saved.'; status.style.color = '#16a34a'; }
            setTimeout(close, 600);
        })
        .catch(function () {
            if (saveBtn) saveBtn.disabled = false;
            if (status) { status.textContent = 'Network error.'; status.style.color = '#dc2626'; }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var editBtn = document.getElementById('editGroupsBtn');
        var saveBtn = document.getElementById('saveGroupsBtn');
        var cancelBtn = document.getElementById('cancelGroupsBtn');
        if (editBtn) editBtn.addEventListener('click', open);
        if (saveBtn) saveBtn.addEventListener('click', save);
        if (cancelBtn) cancelBtn.addEventListener('click', close);
    });
})();

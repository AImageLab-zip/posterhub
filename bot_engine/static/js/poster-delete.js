// Delete dialog shared by the dashboard and the poster page (_delete_modal_body.html).
// The paper's groups, compared with the caller's, decide what it offers:
//   - every group it is in is one of the caller's -> Delete, plus "Remove from specific groups" when 2+;
//   - it is also in groups the caller is not in   -> only removal from the caller's groups;
//   - none of its groups are the caller's          -> nothing (uploader of a paper of other groups).
// With an onDone callback the form is sent with fetch (dashboard); without one it submits normally.
(function () {
    var state = { posterId: null, onDone: null, scope: null, seq: 0 };

    function el(id) { return document.getElementById(id); }
    function show(id, visible) { var n = el(id); if (n) n.hidden = !visible; }

    function selectedGroupIds() {
        return Array.from(document.querySelectorAll('#deleteGroupChips input:checked'))
            .map(function (cb) { return cb.value; });
    }

    function syncRemoveButton() {
        var scope = state.scope;
        if (!scope) return;
        var picked = selectedGroupIds().length;
        var all = picked === scope.groups.length;
        var btn = el('deleteRemoveBtn');
        // Taking a deletable paper out of every group would orphan it: Delete covers that case.
        btn.disabled = picked === 0 || (scope.can_delete && all);
        btn.textContent = (!scope.can_delete && all) ? 'Remove from my groups' : 'Remove from selected groups';
        el('deleteGroupsHint').textContent = (scope.can_delete && all)
            ? 'To remove it from all its groups, use Delete.'
            : 'It stays in the groups you leave unticked' + (scope.has_other_groups ? ' and in the other groups.' : '.');
    }

    function showGroupPicker(checked) {
        var box = el('deleteGroupChips');
        box.innerHTML = '';
        state.scope.groups.forEach(function (g) {
            var label = document.createElement('label');
            label.className = 'groups-editor-chip';
            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.name = 'group_ids';
            cb.value = g.id;
            cb.checked = checked;
            cb.addEventListener('change', syncRemoveButton);
            label.appendChild(cb);
            label.appendChild(document.createTextNode(' ' + g.name));
            box.appendChild(label);
        });
        show('deleteGroupsBox', true);
        show('deleteRemoveBtn', true);
        show('deleteToggleGroupsBtn', false);
        syncRemoveButton();
    }

    function render(scope) {
        state.scope = scope;
        show('deleteModalStatus', false);
        var note = el('deleteSharedNote');
        if (scope.can_delete) {
            el('deleteModalHeading').textContent = 'Confirm Delete';
            el('deleteModalVerb').textContent = 'Are you sure you want to delete';
            show('deleteIrreversible', true);
            show('deleteConfirmBtn', true);
            show('deleteToggleGroupsBtn', scope.groups.length > 1);
        } else if (scope.groups.length) {
            el('deleteModalHeading').textContent = 'Remove from your groups';
            el('deleteModalVerb').textContent = 'Remove';
            note.textContent = 'This paper is also shared with groups you are not part of, so it cannot be deleted. '
                + 'You can remove it from your groups; it stays available to the others.';
            note.hidden = false;
            showGroupPicker(true);
        } else {
            el('deleteModalHeading').textContent = 'Cannot delete';
            el('deleteModalVerb').textContent = 'You cannot delete';
            note.textContent = 'This paper belongs only to groups you are not part of.';
            note.hidden = false;
        }
    }

    function reset() {
        state.scope = null;
        el('deleteModalHeading').textContent = 'Confirm Delete';
        el('deleteModalVerb').textContent = 'Are you sure you want to delete';
        el('deleteModalStatus').textContent = "Checking the paper's groups…";
        el('deleteGroupChips').innerHTML = '';
        el('deleteGroupsHint').textContent = '';
        show('deleteModalStatus', true);
        ['deleteSharedNote', 'deleteGroupsBox', 'deleteIrreversible',
         'deleteToggleGroupsBtn', 'deleteRemoveBtn', 'deleteConfirmBtn'].forEach(function (id) { show(id, false); });
        el('deleteRemoveBtn').disabled = false;
        el('deleteConfirmBtn').disabled = false;
    }

    window.openPosterDeleteModal = function (posterId, posterTitle, onDone) {
        var seq = ++state.seq;
        state.posterId = posterId;
        state.onDone = onDone || null;
        reset();
        el('deletePosterTitle').textContent = posterTitle;
        el('deleteConfirmBtn').setAttribute('formaction', '/delete/' + posterId + '/');
        el('deleteRemoveBtn').setAttribute('formaction', '/poster/' + posterId + '/remove-groups/');
        el('deleteModal').style.display = 'flex';

        fetch('/poster/' + posterId + '/delete-options/', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (res) { if (!res.ok) throw new Error(res.status); return res.json(); })
            .then(function (scope) { if (seq === state.seq) render(scope); })
            .catch(function () {
                if (seq === state.seq) el('deleteModalStatus').textContent = "Could not load the paper's groups. Try again.";
            });
    };

    window.closeDeleteModal = function () {
        state.seq++;
        state.posterId = null;
        el('deleteModal').style.display = 'none';
    };

    document.addEventListener('DOMContentLoaded', function () {
        var form = el('deleteForm');
        if (!form) return;

        el('deleteToggleGroupsBtn').addEventListener('click', function () { showGroupPicker(false); });

        form.addEventListener('submit', function (e) {
            var submitter = e.submitter;
            if (!submitter || !state.onDone) return;   // poster page: normal POST + redirect
            e.preventDefault();
            var kind = submitter.id === 'deleteRemoveBtn' ? 'remove' : 'delete';
            var url = submitter.getAttribute('formaction');
            var posterId = state.posterId;
            var onDone = state.onDone;
            var body = new FormData(form);
            closeDeleteModal();

            fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': getCSRFToken(), 'X-Requested-With': 'XMLHttpRequest' },
                body: body,
            })
                .then(function (res) { return res.json(); })
                .then(function (data) { onDone(kind, data, posterId); })
                .catch(function () { showToast('Network error', 'error'); });
        });
    });
})();

function onPendingGroupChange(select) {
    var form = select.closest('form');
    if (!form) return;
    if (select.value) {
        form.setAttribute('action', select.value);
    }
}

// Pending users are added in the background so the groups picked in the other rows survive.
function addMemberChip(groupId, member) {
    var card = document.querySelector('.group-card[data-group-id="' + groupId + '"]');
    if (!card) return;
    var box = card.querySelector('.group-card-members');
    var count = box.querySelector('.member-count');
    if (!count) {
        box.innerHTML = '<strong>Members (<span class="member-count">0</span>):</strong>';
        count = box.querySelector('.member-count');
    }
    var chip = document.createElement('span');
    chip.className = 'member-chip' + (member.is_primary ? ' is-primary' : '');
    chip.textContent = member.name + (member.is_primary ? ' ★' : '');
    box.appendChild(document.createTextNode(' '));
    box.appendChild(chip);
    count.textContent = parseInt(count.textContent, 10) + 1;
}

function removePendingRow(userId) {
    var row = document.querySelector('[data-pending-row="' + userId + '"]');
    if (!row) return;
    var card = row.closest('.pending-card');
    row.remove();
    var left = card.querySelectorAll('[data-pending-row]').length;
    if (!left) {
        card.remove();
        return;
    }
    card.querySelector('.pending-count').textContent =
        left + ' user' + (left === 1 ? '' : 's') + ' awaiting group assignment';
}

document.querySelectorAll('form.pending-form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var sel = form.querySelector('select[name="group_select"]');
        if (!sel || !sel.value) return;
        var groupId = sel.options[sel.selectedIndex].dataset.groupId;
        var button = form.querySelector('button[type="submit"]');
        button.disabled = true;

        fetch(sel.value, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    button.disabled = false;
                    showToast(data.error || 'Could not add the user', 'error');
                    return;
                }
                data.added.forEach(function (m) {
                    addMemberChip(groupId, m);
                    removePendingRow(m.user_id);
                });
                data.already.forEach(removePendingRow);
                var msg = data.messages[0];
                if (msg) showToast(msg.text, msg.type);
            })
            .catch(function () {
                button.disabled = false;
                showToast('Network error', 'error');
            });
    });
});

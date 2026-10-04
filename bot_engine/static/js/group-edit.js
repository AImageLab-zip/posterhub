// Show how many users are picked on the "Add" button: iOS Safari's closed multi-select
// keeps showing "0 Items" after the picker is dismissed (WebKit bug), so this is the
// reliable count on every device.
(function () {
    var select = document.getElementById('addMemberSelect');
    var btn = document.getElementById('addMemberBtn');
    if (!select || !btn) return;

    function update() {
        var n = select.selectedOptions.length;
        btn.textContent = n ? 'Add ' + n + ' selected' : 'Add Selected';
    }
    ['change', 'input', 'blur'].forEach(function (ev) { select.addEventListener(ev, update); });
    update();
})();

document.querySelectorAll('[data-toggle="sidebar-collapse"]').forEach((button) => {
    button.addEventListener('click', (event) => {
        event.preventDefault();
        document.querySelectorAll('.sidebar-separator-title').forEach((element) => element.classList.toggle('invisible'));
        document.querySelectorAll('.menu-collapsed').forEach((element) => element.classList.toggle('d-none'));
        ['wrapper', 'sidebar-wrapper', 'page-content-wrapper'].forEach((id) => {
            const element = document.getElementById(id);
            element.classList.toggle('sidebar-expanded');
            element.classList.toggle('sidebar-collapsed');
        });
        document.querySelectorAll('.sidebar-item').forEach((element) => {
            element.classList.toggle('justify-content-start');
            element.classList.toggle('justify-content-center');
        });
        document.getElementById('collapse-x').classList.toggle('d-none');
        document.getElementById('collapse-menu').classList.toggle('d-none');
    });
});

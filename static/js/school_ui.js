
(function () {
    "use strict";

    function initializeSchoolMenu() {
        const sidebar = document.getElementById("schoolSidebar");
        const overlay = document.getElementById("schoolOverlay");
        const openButton = document.getElementById("schoolMenuButton");
        const closeButton = document.getElementById("schoolMenuClose");

        if (!sidebar || !overlay || !openButton || !closeButton) {
            return;
        }

        function setMenuOpen(isOpen) {
            sidebar.classList.toggle("open", isOpen);
            overlay.classList.toggle("open", isOpen);

            sidebar.setAttribute("aria-hidden", String(!isOpen));
            openButton.setAttribute("aria-expanded", String(isOpen));

            if (isOpen) {
                closeButton.focus();
            } else {
                openButton.focus();
            }
        }

        openButton.addEventListener("click", function () {
            setMenuOpen(true);
        });

        closeButton.addEventListener("click", function () {
            setMenuOpen(false);
        });

        overlay.addEventListener("click", function () {
            setMenuOpen(false);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" &&
                sidebar.classList.contains("open")) {
                setMenuOpen(false);
            }
        });

        const currentPath = window.location.pathname;

        sidebar.querySelectorAll("a").forEach(function (link) {
            if (link.pathname === currentPath) {
                link.classList.add("active");
                link.setAttribute("aria-current", "page");
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeSchoolMenu);
    } else {
        initializeSchoolMenu();
    }
})();

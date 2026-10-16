(function () {
  "use strict";

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    return parts.length === 2 ? parts.pop().split(";").shift() : null;
  }

  document.addEventListener("htmx:configRequest", function (event) {
    const method = (event.detail.verb || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
      const token = getCookie("donoflow_csrftoken") || getCookie("csrftoken");
      if (token) event.detail.headers["X-CSRFToken"] = token;
    }
  });

  document.addEventListener("htmx:afterSwap", function () {
    const main = document.getElementById("main-content");
    if (main && window.location.hash === "#main-content") main.focus();
  });

  document.addEventListener("htmx:responseError", function () {
    window.setTimeout(function () {
      window.alert("Non è stato possibile completare l’operazione. Riprova tra qualche istante.");
    }, 50);
  });
})();

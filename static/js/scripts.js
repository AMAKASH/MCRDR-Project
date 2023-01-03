let page = window.location.pathname;

//console.log("Log from global js");

if (page != "/") {
  let home_nav = document.getElementById("nav-home");
  let rule_nav = document.getElementById("nav-rules");
  let corner_nav = document.getElementById("nav-cornerstones");
  home_nav.classList.remove("active");
  home_nav.removeAttribute("aria-current");

  if (page == "/rules") {
    rule_nav.classList.add("active");
  } else {
    corner_nav.classList.add("active");
  }
}

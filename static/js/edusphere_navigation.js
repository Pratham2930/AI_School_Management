(function(){'use strict';
function init(){const menu=document.getElementById('edu-sidebar'),overlay=document.getElementById('edu-menu-overlay'),trigger=document.getElementById('edu-menu-trigger'),close=document.getElementById('edu-menu-close');if(!menu||!overlay||!trigger||!close)return;
let lastFocus=null;
function setOpen(open){menu.classList.toggle('edu-open',open);overlay.classList.toggle('edu-open',open);menu.setAttribute('aria-hidden',String(!open));trigger.setAttribute('aria-expanded',String(open));if(open){lastFocus=document.activeElement;close.focus()}else if(lastFocus&&lastFocus.focus){lastFocus.focus()}}
trigger.addEventListener('click',()=>setOpen(true));close.addEventListener('click',()=>setOpen(false));overlay.addEventListener('click',()=>setOpen(false));document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menu.classList.contains('edu-open'))setOpen(false);if(e.key==='Tab'&&menu.classList.contains('edu-open')){const focusable=[...menu.querySelectorAll('a[href],button:not([disabled])')];if(!focusable.length)return;const first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}});
const path=window.location.pathname;menu.querySelectorAll('a.edu-link').forEach(a=>{if(a.pathname===path){a.classList.add('edu-active');a.setAttribute('aria-current','page')}});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();})();

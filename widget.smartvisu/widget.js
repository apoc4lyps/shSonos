/*
-----------------------------------------------
ADD this line to widget.js
-----------------------------------------------
 */

$(document).delegate('[data-widget="sonos.cover"]',{update:function(d, a){$(this).attr('src', a);}});

$(document).ready(function() {
  socket = new WebSocket("ws://" + window.location.host + "/ws/");
  socket.onmessage = function(e) {
    var obj = JSON.parse(e.data);
    var msg = 'User: ' + obj.user + '<br>file: ' + obj.file;
    $('<br><br><div class="alert alert-info">'+ msg +'</div>')
      .insertBefore('#main-nav')
      .delay(5000)
      .fadeOut();
    console.log(e);
  }
})

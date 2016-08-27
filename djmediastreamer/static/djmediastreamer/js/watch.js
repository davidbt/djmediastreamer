function change_playback_rate(id, delta) {
  document.getElementById(id).playbackRate += delta;
  $('#speed-label').html(document.getElementById(id).playbackRate.toFixed(2) + 'x');
}

$(document).ready(function(){
  var csrftoken = document.getElementsByName('csrfmiddlewaretoken')[0].value;
  $.ajaxSetup({
    beforeSend: function(xhr, settings) {
      if (!this.crossDomain) {
        xhr.setRequestHeader("X-CSRFToken", csrftoken);
      }
    }
  });

  $('#faster-btn').click(function(e) {
    change_playback_rate('video', 0.05);
  });

  $('#slower-btn').click(function(e) {
    change_playback_rate('video', -0.05);
  });

  setInterval(function() {
    var ct = $('#video')[0].currentTime;
    var put_data = {position: ct};
    console.log(put_data);
    $.ajax({
      url: '.',
      type: 'PUT',
      data: put_data,
    });
    console.log(ct);
  }, 1000*60);
});

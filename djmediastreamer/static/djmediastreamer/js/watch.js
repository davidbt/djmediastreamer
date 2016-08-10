$(document).ready(function(){
  var csrftoken = document.getElementsByName('csrfmiddlewaretoken')[0].value;
  $.ajaxSetup({
    beforeSend: function(xhr, settings) {
      if (!this.crossDomain) {
        xhr.setRequestHeader("X-CSRFToken", csrftoken);
      }
    }
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

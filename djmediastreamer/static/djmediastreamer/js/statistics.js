function get_chart(serie_name, serie_data, chart_name) {
  return {
    chart: {
        type: 'column'
    },
    title: {
        text: ''
    },
    xAxis: {
        type: 'category'
    },
    yAxis: {
        title: {
            text: ''
        }
    },
    legend: {
        enabled: false
    },
    plotOptions: {
      series: {
          borderWidth: 0,
          dataLabels: {
              enabled: true
          }
      },
      column: {
        point: {
          events: {
            click: function(e) {
              // get the form values
              var query = $('#filters-form').serializeArray().reduce(function(m,o){ m[o.name] = o.value; return m;}, {});
              query.column_name = e.point.name;
              query.chart = chart_name;
              $.ajax({
                url: 'query',
                type: 'GET',
                data: query,
                success: function(r) {
                  // ugly code while the datatables error get fixed.
                  var html = '<table id="mediafiles-table" class="display" width="100%">{content}</table>';
                  var head = '<thead><tr>{columns}<tr></thead>';
                  var columns = '';
                  $.each(r.columns, function(i, e) {
                    columns += '<th>' + e + '</th>';
                  });
                  head = head.replace('{columns}', columns);
                  var rows = '';
                  $.each(r.mediafiles, function(i, e) {
                    var row = '<tr>{cells}</tr>';
                    var cells = '';
                    $.each(e, function(j, v) {
                      cells += '<td>' + v + '</td>';
                    });
                    row = row.replace('{cells}', cells);
                    rows += row;
                  });
                  var body = '<tbody>{rows}</tbody>';
                  body = body.replace('{rows}', rows);
                  var content = head + body;
                  html = html.replace('{content}', content);
                  $('#details-content').html(html);
                  /* Gives this errors: TypeError: invalid 'in' operand a ... Seems to be a datatables bug
                  $('#mediafiles-table').DataTable({
                    data: r.mediafiles,
                    columns: r.columns
                  });*/
                  $('#modal-details').modal();
                }
              });
            }
          }
        }
      }
    },
    series: [{
        name: serie_name,
        colorByPoint: true,
        data: serie_data
    }]
  };
}

$(document).ready(function(){
  $('form#filters-form :input').change(function() {
    $('#filters-form').submit();
  });

  charts.forEach(function(e){
    // e.data[0] because is just one serie for the moment.
    $('#'+e.container).highcharts(get_chart('Count', e.data[0], e.name));
  });

});

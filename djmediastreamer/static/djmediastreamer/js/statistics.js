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
              console.log(e.point);
              console.log(chart_name);
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
  $('#id_directory').change(function() {
    $('#filters-form').submit();
  });

  charts.forEach(function(e){
    console.log(e);
    // e.data[0] because is just one serie for the moment.
    $('#'+e.container).highcharts(get_chart('Count', e.data[0], e.chart_name));
  });

});

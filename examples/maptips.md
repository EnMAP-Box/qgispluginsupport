# show Spectral Profiloes as Map Tips

- open the layer properties

- Goto Display and edit the HTML Map Tip:
````html
<p>Profile [% @id %] [% "name" %]</p>

<p> Data:</br>
<h1>Location [% @id %] <i>"[% "name" %]"</i></h1>
Plot</br>
<!-- [%   '['+array_to_string( spectralData("profiles")['x'])+']' %]-->
<!-- Plotly.js -->
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<!-- Plotly chart will be drawn inside this DIV -->
<div id="graphDiv"></div>
<script>
var data = [
  {
    x: [%   '['+ array_to_string( spectralData("profiles")['x'])+']' %],
    y: [%   '['+ array_to_string( spectralData("profiles")['y'])+']' %],
    type: 'scatter'
  }
];

var layout = {
  autosize: false,
  width: 500,
  height: 250,
  margin: {
    l: 5,
    r: 5,
    b: 10,
    t: 10,
    pad: 1
  },
  paper_bgcolor: '#7f7f7f',
  plot_bgcolor: '#c7c7c7'
};

Plotly.react(graphDiv, data, layout);

var myPlot = document.getElementById('graphDiv');
  </script>

````
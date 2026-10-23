(function () {
    "use strict";
    var canvas = document.getElementById("category-revenue");
    var source = document.getElementById("category-chart-data");
    if (!canvas || !source || !window.Chart) return;
    var data = JSON.parse(source.textContent);
    var chart = new Chart(canvas, {
        type: "bar",
        data: {labels: data.labels, datasets: [{label: "Revenue (SGD)", data: data.revenue.map(Number), borderWidth: 2}]},
        options: {responsive: true, maintainAspectRatio: false, animation: false,
            plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true}}}
    });
    function theme() {
        var style = getComputedStyle(document.documentElement);
        var ink = style.getPropertyValue("--color-text-primary").trim();
        var border = style.getPropertyValue("--color-border-subtle").trim();
        chart.data.datasets[0].backgroundColor = style.getPropertyValue("--color-text-secondary").trim();
        chart.data.datasets[0].borderColor = ink;
        ["x", "y"].forEach(function (axis) {chart.options.scales[axis].ticks.color = ink; chart.options.scales[axis].grid.color = border;});
        chart.update("none");
    }
    theme();
    new MutationObserver(theme).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", theme);
}());

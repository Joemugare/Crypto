function updateChart(data) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(item => item.cryptocurrency),
            datasets: [{
                label: 'Price (USD)',
                data: data.map(item => item.price_usd),
                borderColor: 'green',
                fill: false
            }]
        },
        options: {
            scales: {
                y: { beginAtZero: false }
            }
        }
    });
}
// tracker/static/js/scripts.js
document.addEventListener('DOMContentLoaded', () => {
    // Fetch sentiment data
    fetch('/api/market-data/')
        .then(response => response.json())
        .then(data => {
            const sentimentScore = document.getElementById('sentiment-score');
            const sentimentBar = document.getElementById('sentiment-bar');
            if (data.sentiment) {
                sentimentScore.textContent = data.sentiment.label;
                sentimentBar.style.width = `${data.sentiment.score * 100}%`;
                sentimentBar.classList.remove('bg-success', 'bg-danger', 'bg-warning');
                sentimentBar.classList.add(
                    data.sentiment.score > 0.6 ? 'bg-success' :
                    data.sentiment.score < 0.4 ? 'bg-danger' : 'bg-warning'
                );
            }
        })
        .catch(error => console.error('Error fetching sentiment:', error));

    // Lazy load charts
    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const chartContainer = entry.target;
                chartContainer.classList.add('animate-table');
                observer.unobserve(chartContainer);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.chart-container').forEach(container => {
        observer.observe(container);
    });

    // Ticker click handler
    document.querySelectorAll('.ticker-item').forEach(item => {
        item.addEventListener('click', () => {
            const coin = item.querySelector('.price-slide').dataset.coin;
            window.location.href = `/live-charts/?coin=${coin}`;
        });
    });
});
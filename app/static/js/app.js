(function () {
  let mainChart;
  let playbackInterval;

  function formatCurrency(num) {
    return '$' + parseFloat(num).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }

  function formatInt(num) {
    return parseInt(num).toLocaleString('en-US');
  }

  function payload() {
    const node = document.getElementById("simulation-payload");
    if (!node) return null;
    return JSON.parse(node.textContent);
  }

  function destroy(chart) {
    if (chart) chart.destroy();
  }

  function initChart() {
    destroy(mainChart);

    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = "#a1a1aa"; // zinc-400

    const canvas = document.getElementById("mainSimulationChart");
    if (!canvas) return false;

    mainChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Active Users",
            data: [],
            borderColor: "#3b82f6", // blue
            backgroundColor: "rgba(59, 130, 246, 0.03)",
            borderWidth: 2,
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            pointHoverRadius: 4,
            yAxisID: "y-users"
          },
          {
            label: "Liquidity Pool",
            data: [],
            borderColor: "#10b981", // emerald
            backgroundColor: "rgba(16, 185, 129, 0.03)",
            borderWidth: 2,
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            pointHoverRadius: 4,
            yAxisID: "y-capital"
          },
          {
            label: "Period Outflow",
            data: [],
            borderColor: "#f43f5e", // rose
            borderWidth: 1.5,
            borderDash: [4, 4],
            tension: 0.1,
            pointRadius: 0,
            pointHoverRadius: 4,
            yAxisID: "y-capital"
          }
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 100,
          easing: 'linear'
        },
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          tooltip: {
            backgroundColor: 'rgba(24, 24, 27, 0.95)',
            titleFont: { family: "'JetBrains Mono', monospace", size: 13 },
            bodyFont: { family: "'JetBrains Mono', monospace", size: 12 },
            borderColor: 'rgba(63, 63, 70, 0.5)',
            borderWidth: 1,
            padding: 10,
          },
          legend: {
            labels: {
              boxWidth: 8,
              usePointStyle: true,
              color: "#a1a1aa",
              font: { family: "'Inter', sans-serif", size: 11 }
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#71717a", maxTicksLimit: 8, font: { family: "'JetBrains Mono', monospace", size: 10 } },
            grid: { color: "rgba(255, 255, 255, 0.04)", drawBorder: false },
          },
          "y-users": {
            type: "linear",
            position: "left",
            title: { display: true, text: "Active Users", color: "#3b82f6", font: { family: "'Inter', sans-serif", size: 10, weight: 600 }, textTransform: 'uppercase' },
            ticks: { color: "#71717a", font: { family: "'JetBrains Mono', monospace", size: 10 } },
            grid: { color: "rgba(255, 255, 255, 0.04)", drawBorder: false },
            border: { display: false }
          },
          "y-capital": {
            type: "linear",
            position: "right",
            title: { display: true, text: "Capital ($)", color: "#10b981", font: { family: "'Inter', sans-serif", size: 10, weight: 600 }, textTransform: 'uppercase' },
            ticks: { color: "#71717a", font: { family: "'JetBrains Mono', monospace", size: 10 } },
            grid: { drawOnChartArea: false }, // avoid duplicate grid lines overlapping
            border: { display: false }
          }
        },
      }
    });
    
    return true;
  }

  function startSimulation() {
    if (playbackInterval) clearInterval(playbackInterval);
    
    const data = payload();
    if (!data || !window.Chart) return;
    if (!initChart()) return;

    const timeline = data.timeline;
    let currentIndex = 0;

    // Reset UI Elements
    document.getElementById("live-period").textContent = "0";
    document.getElementById("live-participants").textContent = "0";
    document.getElementById("live-payout").textContent = "$0.00";
    document.getElementById("live-status").textContent = "ACTIVE";
    document.getElementById("live-status").className = "px-3 py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-xs font-bold uppercase tracking-wider";

    playbackInterval = setInterval(() => {
      if (currentIndex >= timeline.length) {
        clearInterval(playbackInterval);
        return;
      }

      const state = timeline[currentIndex];
      const prevState = currentIndex > 0 ? timeline[currentIndex - 1] : null;

      // Calculate Period Outflow (Outflow this specific period)
      const periodOutflow = prevState ? Math.max(0, state.total_payouts - prevState.total_payouts) : state.total_payouts;

      // Push state to chart
      mainChart.data.labels.push(state.label);
      mainChart.data.datasets[0].data.push(state.total_participants);
      mainChart.data.datasets[1].data.push(state.cash_pool);
      mainChart.data.datasets[2].data.push(periodOutflow);
      mainChart.update();

      // Update Tickers
      document.getElementById("live-period").textContent = state.label;
      document.getElementById("live-participants").textContent = formatInt(state.total_participants);
      document.getElementById("live-payout").textContent = formatCurrency(periodOutflow);

      // Status
      const statusEl = document.getElementById("live-status");
      if (state.collapse) {
        statusEl.textContent = "COLLAPSED";
        statusEl.className = "px-3 py-1 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 font-mono text-xs font-bold uppercase tracking-wider";
      } else {
        statusEl.textContent = "ACTIVE";
        statusEl.className = "px-3 py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-xs font-bold uppercase tracking-wider";
      }

      currentIndex++;
    }, 120); // playback interval speed
  }

  window.ChainFlow = { startSimulation, replaySimulation: startSimulation };
  
  window.addEventListener("DOMContentLoaded", () => {
     if(document.getElementById("simulation-payload")) {
         startSimulation();
     }
  });

})();

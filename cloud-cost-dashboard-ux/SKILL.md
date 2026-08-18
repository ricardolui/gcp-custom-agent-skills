---
name: cloud-cost-dashboard-ux
description: UX design patterns and best practices for cloud cost dashboards and daily telemetry explorers, such as defaulting date selection to yesterday (previous day) to avoid incomplete billing data lags.
---

# Cloud Cost & Daily Telemetry Dashboard UX Best Practices

This guide documents the design systems and user experience (UX) guidelines for building cloud cost, spending trackers, and daily telemetry exploration dashboards.

---

## 📅 The "Incomplete Today" Telemetry Dilemma

In cloud environments (e.g., GCP Billing exports to BigQuery, AWS Cost & Usage Reports), billing data is digested asynchronously. The current day's data is always **incomplete, partial, or lagging** by 4 to 24 hours.

### The Problem
If a daily cost or change explorer defaults to **"Today"**, the interface will display artificial cost drops, zeroed metrics, or incomplete series. This leads to user frustration, false-positive alerts, or misleading conclusions.

### The Pattern: Default to Yesterday (Previous Day)
To avoid displaying partial current-day telemetry:
- **Always default date selectors to Yesterday (`dates[1]`):** If the historical data is sorted in reverse chronological order (newest first at index `0`), the default selected item should be the second element (`index 1`), representing the previous day.
- **Provide Visual Indicators:** If current-day (partial) data is selectable, clearly mark it with a badge (e.g., `(Partial Data)` or `(Incomplete)`).

```javascript
// Robust default date selection implementation
function initDateSelector(availableDates) {
    var dateSelect = document.getElementById('dateSelector');
    dateSelect.innerHTML = '';
    
    // Sort descending (newest first)
    var dates = availableDates.slice().reverse(); 
    
    dates.forEach(function(dt, idx) {
        var o = document.createElement('option');
        o.value = dt;
        o.textContent = dt;
        
        // Default select Yesterday (index 1) to avoid partial today telemetry
        if (dates.length > 1 && idx === 1) {
            o.selected = true;
        }
        dateSelect.appendChild(o);
    });
}
```

---

## 📈 Visual & Analytical Cost-Explorer Best Practices

When rendering granular daily lists, top movers, or change indicators, implement these core layout rules:

### 1. Default Sort by Absolute Cost Change ($) Descending
* **Goal:** Surface unexpected spend spikes immediately (e.g., finding a large GPU instance or heavy database cluster that was forgotten and left running yesterday).
* **Implementation:** Always sort change lists by the absolute delta value `Math.abs(current - prior)` in descending order, rather than alphabetical or total cost order. This ensures positive spikes and negative savings drops both bubble to the top.

### 2. Client-Side High-Performance Slicing (Zero Overhead)
* **Avoid Database Round-Trips:** Do not invoke backend databases (like BigQuery or Spanner) on every date change or text filter keypress. This incurs unnecessary API costs and introduces high latency (1–3 seconds).
* **Pattern:** Pre-serialize granular daily service and SKU datasets as JSON maps inside the rendered HTML page on initial load. Let the browser handle search-as-you-type, sorting, and project-filtering locally with instantaneous response.

```javascript
// Fast client-side searching & sorting
function updateExplorer() {
    var query = document.getElementById('searchQuery').value.toLowerCase();
    var filtered = allData.filter(function(row) {
        return row.name.toLowerCase().includes(query);
    });
    
    // Sort by cost change delta descending
    filtered.sort(function(a, b) {
        return Math.abs(b.delta) - Math.abs(a.delta);
    });
    
    renderTable(filtered);
}
```

### 3. Synchronized Interactive Graph-to-Table Controls
* **Sync Range Changes:** Drag-zooming or modifying dates on trend charts should instantly filter and update accompanying tabular lists and text indicators.
* **Double-Click Reset:** Always register double-click handlers on graphs to instantly reset the zoom limits, restore full bounds, and reset date presets back to default ("All").

### 4. Color-Coded Spending Shifts (Accessible Aesthetics)
* Use soft, premium hues instead of high-contrast generic colors:
  - **Increase ($):** Soft material red (e.g., `#c5221f`) accompanied by a clear indicator (e.g., `▲ +$50.00`).
  - **Decrease ($):** Soft material green (e.g., `#137333`) accompanied by a clear indicator (e.g., `▼ -$25.00`).
* Avoid plain primary colors (`red`/`green`) to maintain a professional, cohesive enterprise visual aesthetic.

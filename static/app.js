const outputEl = document.getElementById("output");
const statusTag = document.getElementById("statusTag");
const healthStateEl = document.getElementById("healthState");
const modeTagEl = document.getElementById("modeTag");
const likesCountEl = document.getElementById("likesCount");
const wishCountEl = document.getElementById("wishCount");
const cartCountEl = document.getElementById("cartCount");
const productGrid = document.getElementById("productGrid");
const cartPanel = document.getElementById("cartPanel");
const searchInput = document.getElementById("searchInput");

const signalsPanel = document.getElementById("signalsPanel");
const competitorPanel = document.getElementById("competitorPanel");
const strategyPanel = document.getElementById("strategyPanel");
const logPanel = document.getElementById("logPanel");
const memoryPanel = document.getElementById("memoryPanel");
const applyAgentBtn = document.getElementById("applyAgentBtn");

let storeCache = {
    source: "--",
    products: [],
    cart: { items: [], count: 0, total: 0 },
    likes_count: 0,
    wishlist_count: 0
};

function setStatus(text) {
    statusTag.textContent = text;
}

function setOutput(data) {
    outputEl.textContent = JSON.stringify(data, null, 2);
}

function money(value) {
    return Number(value || 0).toLocaleString("en-IN", {
        style: "currency",
        currency: "INR",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

async function api(path, options = {}) {
    setStatus("Running...");
    try {
        const response = await fetch(path, options);
        const data = await response.json();
        setOutput({ endpoint: path, status: response.status, data });
        setStatus(response.ok ? "Success" : "Failed");
        return { ok: response.ok, data, status: response.status };
    } catch (error) {
        setStatus("Error");
        setOutput({ endpoint: path, error: String(error) });
        return { ok: false, data: { message: String(error) } };
    }
}

function renderCart() {
    cartPanel.innerHTML = "";
    const items = storeCache.cart.items || [];
    if (!items.length) {
        cartPanel.innerHTML = `<article class="item"><p>Your cart is empty.</p></article>`;
        return;
    }

    for (const item of items) {
        const node = document.createElement("article");
        node.className = "item";
        node.innerHTML = `
            <p><strong>${item.name}</strong></p>
            <p class="small">Qty: ${item.quantity} | ${money(item.subtotal)}</p>
            <button class="btn-small" data-cart-remove="${item.product_id}">Remove</button>
        `;
        cartPanel.appendChild(node);
    }

    const totalNode = document.createElement("article");
    totalNode.className = "item";
    totalNode.innerHTML = `<p><strong>Total</strong></p><p class="small">${money(storeCache.cart.total)}</p>`;
    cartPanel.appendChild(totalNode);

    document.querySelectorAll("[data-cart-remove]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const productId = Number(btn.getAttribute("data-cart-remove"));
            await api("/cart/remove", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ product_id: productId })
            });
            await loadStore();
        });
    });
}

function productCard(product) {
    const liked = product.liked ? "Liked" : "Like";
    const wish = product.wishlisted ? "Wishlisted" : "Add Wishlist";
    return `
        <article class="product">
            <img src="${product.image_url}" alt="${product.name}">
            <div class="product-body">
                <h4>${product.name}</h4>
                <p class="meta">${product.category} | Stock ${product.stock}</p>
                <div class="metric"><span>Price</span><strong>${money(product.price)}</strong></div>
                <div class="actions">
                    <button class="btn-small like" data-like="${product.id}">${liked}</button>
                    <button class="btn-small wish" data-wishlist="${product.id}">${wish}</button>
                    <button class="btn-small primary" data-cart="${product.id}">Add to Cart</button>
                </div>
            </div>
        </article>
    `;
}

function renderProducts(filter = "") {
    const text = filter.trim().toLowerCase();
    const products = storeCache.products.filter((p) => {
        if (!text) {
            return true;
        }
        return String(p.name).toLowerCase().includes(text) || String(p.category).toLowerCase().includes(text);
    });

    productGrid.innerHTML = products.map(productCard).join("");
    if (!products.length) {
        productGrid.innerHTML = `<article class="item"><p>No matching products.</p></article>`;
        return;
    }

    document.querySelectorAll("[data-like]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = Number(btn.getAttribute("data-like"));
            await api("/toggle-like", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ product_id: id })
            });
            await loadStore();
        });
    });

    document.querySelectorAll("[data-wishlist]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = Number(btn.getAttribute("data-wishlist"));
            await api("/wishlist/toggle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ product_id: id })
            });
            await loadStore();
        });
    });

    document.querySelectorAll("[data-cart]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = Number(btn.getAttribute("data-cart"));
            await api("/cart/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ product_id: id, quantity: 1 })
            });
            await loadStore();
        });
    });
}

function updateTopStats() {
    modeTagEl.textContent = `Mode: ${storeCache.source}`;
    likesCountEl.textContent = `Like ${storeCache.likes_count || 0}`;
    wishCountEl.textContent = `Wish ${storeCache.wishlist_count || 0}`;
    cartCountEl.textContent = `Cart ${storeCache.cart?.count || 0}`;
}

async function loadHealth() {
    const res = await api("/health");
    const mode = res.data?.mode || "unknown";
    healthStateEl.textContent = mode === "db" ? "Live DB Mode" : "Demo Mode (DB Offline)";
}

async function loadStore() {
    const res = await api("/store-data");
    if (!res.ok) {
        return;
    }

    storeCache = {
        source: res.data.source,
        products: res.data.products || [],
        cart: res.data.cart || { items: [], count: 0, total: 0 },
        likes_count: res.data.likes_count || 0,
        wishlist_count: res.data.wishlist_count || 0
    };

    updateTopStats();
    renderProducts(searchInput.value);
    renderCart();
}

async function refreshApplyButtonState() {
    const res = await api("/agent-state");
    applyAgentBtn.disabled = !(res.ok && res.data?.has_pending);
}

function drawList(target, rows, renderer) {
    target.innerHTML = "";
    if (!rows.length) {
        target.innerHTML = `<article class="item"><p>No data</p></article>`;
        return;
    }
    rows.forEach((row) => {
        const node = document.createElement("article");
        node.className = "item";
        node.innerHTML = renderer(row);
        target.appendChild(node);
    });
}

function buildMemory(logs) {
    if (!logs.length) {
        return "No execution memory yet.";
    }
    const success = logs.filter((x) => x.success).length;
    const avg = (logs.reduce((acc, x) => acc + Number(x.action_value || 0), 0) / logs.length).toFixed(2);
    return [
        `Total decisions: ${logs.length}`,
        `Successful actions: ${success}`,
        `Average discount/action: ${avg}%`,
        "Learning: discount when demand weak and stock high."
    ].join("\n");
}

async function loadAgentPanels() {
    const [signalsRes, compRes, strategyRes, logsRes] = await Promise.all([
        api("/business-signals"),
        api("/competitor-prices"),
        api("/strategy-preview"),
        api("/agent-logs?limit=20")
    ]);

    drawList(signalsPanel, signalsRes.data?.data || [], (x) => `
        <p><strong>${x.name}</strong></p>
        <p class="small">Trend: ${x.sales_trend}, Demand: ${x.demand}, Stock: ${x.stock} (${x.stock_risk})</p>
    `);

    drawList(competitorPanel, compRes.data?.data || [], (x) => `
        <p><strong>${x.name}</strong></p>
        <p class="small">Our ${money(x.our_price)} | Rival ${money(x.competitor_price)} | Gap ${x.gap_percent}%</p>
    `);

    drawList(strategyPanel, strategyRes.data?.data || [], (x) => `
        <p><strong>${x.name}</strong> -> ${x.selected?.strategy || "none"}</p>
        <p class="small">Projected profit: ${money(x.selected?.projected_profit || 0)}</p>
    `);

    const logs = logsRes.data?.data || [];
    drawList(logPanel, logs, (x) => `
        <p><strong>Product ${x.product_id}</strong> | ${x.action}</p>
        <p class="small">${money(x.before_price)} -> ${money(x.after_price)} | ${x.reason || ""}</p>
    `);
    memoryPanel.textContent = buildMemory(logs);
}

async function simulateCheckout() {
    const items = storeCache.cart.items || [];
    if (!items.length) {
        setOutput({ message: "Cart is empty." });
        return;
    }

    for (const item of items) {
        await api("/simulate-purchase", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ product_id: item.product_id, quantity: item.quantity })
        });
    }
    await loadStore();
    await loadAgentPanels();
}

document.querySelectorAll(".menu-btn[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".menu-btn[data-view]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
        document.getElementById(btn.getAttribute("data-view")).classList.add("active");
    });
});

searchInput.addEventListener("input", () => renderProducts(searchInput.value));
document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadStore();
    await loadAgentPanels();
    await loadHealth();
    await refreshApplyButtonState();
});
document.getElementById("healthBtn").addEventListener("click", loadHealth);
document.getElementById("simulateBtn").addEventListener("click", async () => {
    await api("/simulate-sales");
    await loadStore();
    await loadAgentPanels();
    await refreshApplyButtonState();
});
document.getElementById("runAgentBtn").addEventListener("click", async () => {
    const res = await api("/run-agent");
    const decisions = res.data?.data || [];
    applyAgentBtn.disabled = decisions.length === 0;
    drawList(logPanel, decisions, (x) => `
        <p><strong>${x.name || `Product ${x.product_id}`}</strong> | ${x.action}</p>
        <p class="small">${money(x.before_price)} -> ${money(x.after_price)} | ${x.reason || ""}</p>
    `);
    memoryPanel.textContent = buildMemory(decisions);
    await loadStore();
    await refreshApplyButtonState();
});
applyAgentBtn.addEventListener("click", async () => {
    const res = await api("/apply-agent-decisions", { method: "POST" });
    if (res.ok) {
        applyAgentBtn.disabled = true;
    }
    await loadStore();
    await loadAgentPanels();
    await refreshApplyButtonState();
});
document.getElementById("reloadSignalsBtn").addEventListener("click", loadAgentPanels);
document.getElementById("checkoutBtn").addEventListener("click", simulateCheckout);

async function init() {
    await loadHealth();
    await loadStore();
    await loadAgentPanels();
    await refreshApplyButtonState();
}

init();

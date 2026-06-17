import asyncio
import sys
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import scraper
import storage

# On Windows, ProactorEventLoop throws WinError 10054 when Selenium's chromedriver
# subprocess closes its pipe. Switch to SelectorEventLoop which avoids this entirely.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_PREFIX_SYMBOLS = {"$", "€", "£", "¥", "₺", "₹"}


def _fmt_price(price: float | None, currency: str) -> str:
    if price is None:
        return "N/A"
    formatted = f"{price:,.2f}"
    if currency in _PREFIX_SYMBOLS:
        return f"{currency}{formatted}"
    return f"{formatted} {currency}" if currency else formatted

st.set_page_config(page_title="Amazon Price Tracker", page_icon="🛒", layout="wide")

# ── Auto-refresh every 5 minutes ──────────────────────────────────────────────
refresh_count = st_autorefresh(interval=300_000, key="autorefresh")

# ── Session state ─────────────────────────────────────────────────────────────
if "last_refresh_count" not in st.session_state:
    st.session_state.last_refresh_count = 0
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None

# ── Background refresh ────────────────────────────────────────────────────────
if refresh_count > st.session_state.last_refresh_count:
    st.session_state.last_refresh_count = refresh_count
    changed = storage.refresh_all_products(scraper.scrape_product)
    for name in changed:
        st.toast(f"Change detected: {name}", icon="⚠️")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🛒 Amazon Product Tracker")
st.caption("Prices and stock levels refresh automatically every 5 minutes.")

# ── Add product form ──────────────────────────────────────────────────────────
with st.form("add_product", clear_on_submit=True):
    url_input = st.text_input("Amazon Product URL", placeholder="https://www.amazon.com/dp/...")
    submitted = st.form_submit_button("Add Product", use_container_width=True)

if submitted and url_input:
    with st.spinner("Fetching product info…"):
        result = scraper.scrape_product(url_input.strip())
    if result["error"]:
        st.error(f"Could not fetch product: {result['error']}")
    else:
        storage.add_product(result["url"], result["name"], result["price"], result["currency"], result["stock"])
        st.success(f"Added: {result['name']}")
        st.rerun()
elif submitted and not url_input:
    st.warning("Please enter a URL.")

st.divider()

# ── Product list ──────────────────────────────────────────────────────────────
products = storage.load_products()

if not products:
    st.info("No products tracked yet. Paste an Amazon URL above to get started.")
else:
    for p in products:
        with st.container(border=True):

            # ── Edit mode ─────────────────────────────────────────────────────
            if st.session_state.edit_id == p["id"]:
                new_name = st.text_input("Product name", value=p["name"], key=f"name_{p['id']}")
                new_url = st.text_input("URL", value=p["url"], key=f"url_{p['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Save", key=f"save_{p['id']}", use_container_width=True, type="primary"):
                    storage.update_product(p["id"], new_name.strip(), new_url.strip())
                    st.session_state.edit_id = None
                    st.rerun()
                if c2.button("Cancel", key=f"cancel_{p['id']}", use_container_width=True):
                    st.session_state.edit_id = None
                    st.rerun()
                continue

            # ── Normal view ───────────────────────────────────────────────────
            col_name, col_price, col_stock, col_actions = st.columns([5, 2, 3, 1])

            with col_name:
                st.markdown(f"**[{p['name']}]({p['url']})**")
                try:
                    checked_at = datetime.fromisoformat(p["last_checked"]).strftime("%d %b %Y, %H:%M")
                except Exception:
                    checked_at = p["last_checked"]
                st.caption(f"Last checked: {checked_at}")

            with col_price:
                currency = p.get("currency", "")
                price_str = _fmt_price(p["price"], currency)

                if p.get("price_changed") and p.get("prev_price") is not None:
                    prev_str = _fmt_price(p["prev_price"], currency)
                    st.markdown(f":orange[**{price_str}**]  ~~{prev_str}~~")
                    st.caption(":orange[Price changed]")
                else:
                    st.markdown(f"**{price_str}**")
                    st.caption("Price")

            with col_stock:
                stock_text = p.get("stock") or "Unknown"
                if p.get("stock_changed"):
                    prev_stock = p.get("prev_stock") or "?"
                    st.markdown(f":orange[**{stock_text}**]")
                    st.caption(f":orange[Was: {prev_stock}]")
                else:
                    color = "green" if "in stock" in stock_text.lower() else "red" if "out of stock" in stock_text.lower() or "unavailable" in stock_text.lower() else "gray"
                    st.markdown(f":{color}[**{stock_text}**]")
                    st.caption("Stock")

            with col_actions:
                st.write("")  # vertical alignment nudge
                if st.button("Edit", key=f"edit_{p['id']}", use_container_width=True):
                    st.session_state.edit_id = p["id"]
                    st.rerun()
                if st.button("Delete", key=f"del_{p['id']}", use_container_width=True, type="secondary"):
                    storage.delete_product(p["id"])
                    st.rerun()

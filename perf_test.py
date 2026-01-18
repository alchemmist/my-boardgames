import asyncio
import time
from tabulate import tabulate
from playwright.async_api import async_playwright

FILES = {
    "baseline": "http://localhost:8001/index.html",
    "fast": "http://localhost:8000/index.html",
}


async def measure(browser, url):
    context = await browser.new_context()
    page = await context.new_page()

    client = await context.new_cdp_session(page)
    await client.send("Network.enable")
    await client.send("Network.setCacheDisabled", {"cacheDisabled": True})

    image_bytes = 0

    async def on_response(response):
        nonlocal image_bytes
        if (
            response.request.resource_type == "image"
            and response.ok
            and "content-length" in response.headers
        ):
            image_bytes += int(response.headers["content-length"])

    page.on("response", on_response)

    start = time.perf_counter()
    await page.goto(url, wait_until="load")
    perf = await page.evaluate("""
        () => new Promise(resolve => {
            const metrics = { fcp: null, lcp: null }
            new PerformanceObserver(list => { metrics.fcp = list.getEntries()[0]?.startTime }).observe({ type: "paint", buffered: true })
            new PerformanceObserver(list => { const e = list.getEntries(); metrics.lcp = e[e.length-1]?.startTime }).observe({ type: "largest-contentful-paint", buffered: true })
            setTimeout(() => resolve(metrics), 3000)
        })
    """)
    end = time.perf_counter()
    await context.close()
    return {
        "FCP (ms)": round(perf["fcp"]) if perf["fcp"] else None,
        "LCP (ms)": round(perf["lcp"]) if perf["lcp"] else None,
        "Load complete (ms)": round((end - start) * 1000),
        "Image bytes (KB)": round(image_bytes / 1024),
    }


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = {name: await measure(browser, url) for name, url in FILES.items()}

        headers = ["Metric", "Before", "After", "Δ"]
        rows = []
        for metric in results["baseline"]:
            b, a = results["baseline"][metric], results["fast"][metric]
            delta = f"{a - b:+}" if b is not None and a is not None else "n/a"
            rows.append([metric, b, a, delta])

        print(tabulate(rows, headers=headers, tablefmt="github"))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

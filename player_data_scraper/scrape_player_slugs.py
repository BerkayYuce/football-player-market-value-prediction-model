
import asyncio
from playwright.async_api import async_playwright
import os

async def get_premier_league_slugs():
    url = "https://www.sofascore.com/tournament/football/england/premier-league/17#id:61627"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"🌐 Opening: {url}")
        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(3000)

        # Tüm takım linklerini al
        team_links = await page.query_selector_all("a[href^='/team/football']")
        team_urls = set()

        for link in team_links:
            href = await link.get_attribute("href")
            if href:
                team_urls.add("https://www.sofascore.com" + href.split("?")[0])

        print(f"📌 {len(team_urls)} teams found")

        all_slugs = set()

        # Her takım sayfasına git, kadro sayfasına yönlen
        for team_url in team_urls:
            try:
                print(f"🔍 Processing team: {team_url}")
                await page.goto(team_url, timeout=60000)
                await page.wait_for_timeout(2000)

                try:
                    squad_button = await page.query_selector("a:has-text('Squad')")
                    if squad_button:
                        await squad_button.click()
                        await page.wait_for_timeout(2000)
                except:
                    print("⚠️ Squad tab not found, searching for players directly")

                player_links = await page.query_selector_all("a[href*='/player/']")

                for a in player_links:
                    href = await a.get_attribute("href")
                    if href and "/player/" in href:
                        parts = href.strip("/").split("/player/")[-1].split("/")
                        if len(parts) >= 2:
                            slug = f"{parts[-2]}/{parts[-1]}"
                            all_slugs.add(slug)

            except Exception as e:
                print(f"⚠️ Error (skipping team page): {e}")
                continue

        await browser.close()

        
        os.makedirs("output", exist_ok=True)
        with open("output/premier_slug_list.txt", "w", encoding="utf-8") as f:
            for slug in sorted(all_slugs):
                f.write(slug + "\n")

        print(f"\n✅ Total of {len(all_slugs)} oyuncu slug saved → output/premier_slug_list.txt")

if __name__ == "__main__":
    asyncio.run(get_premier_league_slugs())
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
import os
import re
from datetime import datetime

# 🔧 Tabs and their corresponding headers to be scraped
TAB_HEADERS = {
    "General": ["MP", "DK", "GLS", "AST", "ASR"],
    "Shooting": ["TOS", "SOT", "BCM"],
    "Team play": ["KEYP", "BCC", "SDR"],
    "Pas": ["APS", "APS%", "ALB", "LBA%", "ACR", "CA%"],
    "Savunma": ["CLS", "YC", "RC", "ELTG", "DRP", "TACK", "INT", "BLS", "ADW"],
    "Additional": ["xG", "xA", "GI", "XGI"]
}

# Helper function: Calculate age based on season start year
def calculate_age_for_season(birth_year, season_start_year):
    if birth_year is None or season_start_year is None:
        return None
    try:
        return season_start_year - birth_year
    except (TypeError, ValueError):
        return None

# 🔁 Main function to scrape player data
async def get_sofascore_career(slug: str) -> pd.DataFrame:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        player_name = slug.split("/")[0].replace("-", " ").title()
        season_data = {}
        player_birth_year = None
        player_nationality = None
        player_position = None

        try:
            url = f"https://www.sofascore.com/en/player/{slug}"
            print(f"🌐 Opening: {url}")
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state('networkidle', timeout=30000)
            await page.wait_for_timeout(1000)

            print("🔎 Fetching Age, Nationality, and Position info...")
            try:
                birth_date_locator = page.locator(r"#__next > main > div.fresnel-container.fresnel-greaterThanOrEqual-mdMin.fresnel-\:r1\: > div > div.d_flex.flex-wrap_wrap.gap_xl.mdOnly\:gap_md > div.d_flex.flex-d_column.mdDown\:flex-sh_1.mdDown\:flex-b_100\%.gap_md.w_\[0px\].flex-g_2 > div:nth-child(2) > div > div.Box.hKmppk > div.Box.Flex.ggRYVx.flkZQO > div:nth-child(2) > div.Text.gzlBsj")
                await birth_date_locator.wait_for(state='visible', timeout=10000)
                birth_date_text = await birth_date_locator.inner_text()
                year_match = re.search(r'\d{4}', birth_date_text)
                if year_match:
                    player_birth_year = int(year_match.group(0))
            except Exception as e:
                print(f"  ❌ Error fetching birth date: {e}")

            try:
                nationality_locator = page.locator("div.Box.gsaNZo").nth(0).locator("span")
                await nationality_locator.wait_for(state='visible', timeout=10000)
                player_nationality = await nationality_locator.inner_text()
            except Exception as e:
                print(f"  ❌ Error fetching nationality: {e}")

            try:
                position_locator = page.locator(r"#__next > main > div.fresnel-container.fresnel-greaterThanOrEqual-mdMin.fresnel-\:r1\: > div > div.d_flex.flex-wrap_wrap.gap_xl.mdOnly\:gap_md > div.d_flex.flex-d_column.mdDown\:flex-sh_1.mdDown\:flex-b_100\%.gap_md.w_\[0px\].flex-g_2 > div:nth-child(2) > div > div.Box.hKmppk > div.Box.Flex.ggRYVx.flkZQO > div.Box.oWZdE > div.Text.beCNLk")
                await position_locator.wait_for(state='visible', timeout=10000)
                player_position = await position_locator.inner_text()
                if player_position and player_position.strip().upper() == 'K':
                    print(f"❗ Player {player_name} is a goalkeeper, skipping data.")
                    await browser.close()
                    return pd.DataFrame()
            except Exception as e:
                print(f"  ❌ Error fetching position: {e}")

            await page.wait_for_selector("button.DropdownButton", state='visible', timeout=15000)
            dropdown_category_buttons = await page.query_selector_all("button.DropdownButton")

            if not dropdown_category_buttons:
                print(f"⚠️ Category dropdown button not found. ({slug})")
                await browser.close()
                return pd.DataFrame()

            categories_to_process = ["Domestic leagues", "International competitions"]
            
            for category_name in categories_to_process:
                print(f"\n🚀 Selecting category: '{category_name}'")
                category_selection_successful = False
                try:
                    for _ in range(3):
                        try:
                            await dropdown_category_buttons[0].click()
                            await page.wait_for_timeout(1000)
                            category_option_selector = f"li[role='option']:has-text('{category_name}')"
                            await page.wait_for_selector(category_option_selector, state='visible', timeout=10000)
                            await page.click(category_option_selector)
                            await page.wait_for_load_state('networkidle', timeout=45000)
                            await page.wait_for_timeout(2000)
                            category_selection_successful = True
                            break
                        except Exception as e:
                            print(f"⚠️ Could not select or find '{category_name}' ({slug}) (Attempt {_+1}): {e}")
                            await page.wait_for_timeout(1000)
                    if not category_selection_successful:
                        print(f"❌ Failed to select '{category_name}' after 3 attempts. Skipping this category.")
                        continue
                except Exception as e:
                    print(f"❌ Critical error during category selection ({slug} - {category_name}): {e}. Skipping this category.")
                    continue

                try:
                    no_results_locator_text = page.locator("div.d_flex.flex-d_column.ai_center.jc_center", has_text="No results found")
                    no_results_locator_icon = page.locator("div.d_flex.flex-d_column.ai_center.jc_center svg[data-icon='magnifying-glass']")
                    if (await no_results_locator_text.count() > 0 and await no_results_locator_text.is_visible()) or \
                       (await no_results_locator_icon.count() > 0 and await no_results_locator_icon.is_visible()):
                        print(f"❗ 'No results found' message or icon detected for '{category_name}'. Skipping this category.")
                        continue
                except Exception as e:
                    print(f"⚠️ Error checking for 'No results found': {e}")

                for _ in range(5):
                    await page.mouse.wheel(0, 1000)
                    await page.wait_for_timeout(300)

                try:
                    league_dropdown_exists_and_enabled = False
                    league_dropdown_button = None
                    league_texts = []

                    try:
                        dropdown_buttons_league = await page.query_selector_all("button.DropdownButton")
                        if len(dropdown_buttons_league) >= 2:
                            league_dropdown_button = dropdown_buttons_league[1]
                            if await league_dropdown_button.is_enabled():
                                league_dropdown_exists_and_enabled = True
                                try:
                                    await league_dropdown_button.click(timeout=5000)
                                    await page.wait_for_timeout(1000)
                                    initial_leagues_elements = await page.query_selector_all("ul[role='listbox'] > li")
                                    for league_el in initial_leagues_elements:
                                        text = await league_el.inner_text()
                                        if text.strip() and "all" not in text.lower() and "all teams" not in text.lower() and text.strip().upper() != "ENG":
                                            league_texts.append(text.strip())
                                except Exception as e:
                                    print(f"⚠️ Could not click league dropdown or fetch options: {e}. Attempting to get currently selected league.")
                            else:
                                current_displayed_league_name = await league_dropdown_button.inner_text()
                                if current_displayed_league_name.strip() and current_displayed_league_name.strip().upper() != "ENG" and "all teams" not in current_displayed_league_name.lower() and "all" not in current_displayed_league_name.lower():
                                    league_texts.append(current_displayed_league_name.strip())
                    except Exception as e:
                        print(f"❌ Error finding or processing league dropdown button: {e}")

                    if not league_texts or (len(league_texts) == 1 and "all teams" in league_texts[0].lower()):
                        print(f"❗ No valid leagues found for '{category_name}' or only 'All Teams' detected. Skipping.")
                        raise Exception("No valid leagues to process in this category.")

                    print(f"🔍 Leagues to process for ({category_name}): {league_texts}")

                    for league_text_to_select in league_texts:
                        if len(league_texts) == 1:
                            try:
                                # Close expanded season details
                                expanded_arrow = await page.query_selector("div.Box.Flex.jBQtbp.cQgcrM")
                                if expanded_arrow:
                                    await expanded_arrow.click()
                                    await page.wait_for_timeout(1000)
                                    print("🔒 Expanded season details closed.")
                            except Exception as e:
                                print(f"⚠️ Could not close expanded season: {e}")

                        if len(league_texts) > 1 and league_dropdown_exists_and_enabled:
                            print(f"➡️ Clicking league: {league_text_to_select} ({category_name})")
                            selection_successful = False
                            for _ in range(3):
                                try:
                                    if league_dropdown_button and await league_dropdown_button.is_enabled():
                                        await league_dropdown_button.click(timeout=5000)
                                        await page.wait_for_timeout(1000)
                                    current_league_elements = await page.query_selector_all("ul[role='listbox'] > li")
                                    for current_league_element in current_league_elements:
                                        current_league_element_text = await current_league_element.inner_text()
                                        if current_league_element_text.strip().lower() == league_text_to_select.lower():
                                            await current_league_element.click()
                                            await page.wait_for_load_state('networkidle', timeout=60000)
                                            await page.wait_for_timeout(2500)
                                            selection_successful = True
                                            print(f"✅ League '{league_text_to_select}' selected successfully.")
                                            break
                                    if selection_successful:
                                        break
                                    else:
                                        print(f"❗ League '{league_text_to_select}' not found in this attempt. Retrying...")
                                        await page.wait_for_timeout(1000)
                                except Exception as inner_e:
                                    print(f"⚠️ Failed to click league '{league_text_to_select}' (Attempt {_+1}): {inner_e}")
                                    await page.wait_for_timeout(1000)
                            if not selection_successful:
                                print(f"❌ Could not click league '{league_text_to_select}' after 3 attempts. Skipping data fetching for this league.")
                                continue
                        else:
                            print(f"➡️ League '{league_text_to_select}' already selected, skipping click.")

                        try:
                            await page.wait_for_selector("div.Box.Flex.cceZpO.kWzByL div[direction='column']", state='visible', timeout=15000)
                            left_rows_after_league_select = await page.query_selector_all("div.Box.Flex.cceZpO.kWzByL div[direction='column']")
                            await page.wait_for_selector("div.Box.Flex.fEBZed.iWGVcA div[direction='column']", state='visible', timeout=15000)
                            right_rows_after_league_select = await page.query_selector_all("div.Box.Flex.fEBZed.iWGVcA div[direction='column']")
                            if not left_rows_after_league_select or not right_rows_after_league_select or len(right_rows_after_league_select) < 2:
                                print(f"⚠️ Season data not found or is insufficient for selected league '{league_text_to_select}'. Skipping this league.")
                                continue
                        except Exception as e:
                            print(f"❌ Error while waiting for season data for selected league '{league_text_to_select}': {e}. Skipping this league.")
                            continue

                        try:
                            await page.wait_for_selector("a:has-text('Performance')", state='visible', timeout=10000)
                            await page.click("a:has-text('Performance')")
                            await page.wait_for_load_state('networkidle', timeout=45000)
                            await page.wait_for_timeout(1500)
                        except Exception:
                            try:
                                await page.wait_for_selector("a:has-text('Matches')", state='visible', timeout=5000)
                                await page.click("a:has-text('Matches')")
                                await page.wait_for_load_state('networkidle', timeout=45000)
                                await page.wait_for_timeout(1500)
                            except Exception:
                                print(f"⚠️ 'Performance' or 'Matches' tab not found or couldn't be clicked ({league_text_to_select}). Skipping data fetching for this league.")
                                continue

                        try:
                            await page.wait_for_selector("button:has-text('General')", state='visible', timeout=7000)
                            await page.click("button:has-text('General')")
                            await page.wait_for_load_state('networkidle', timeout=45000)
                            await page.wait_for_timeout(1000)
                        except Exception as e:
                            print(f"⚠️ Could not click or find 'General' tab: {e}")

                        season_keys_ordered = []
                        await page.wait_for_selector("div.Box.Flex.cceZpO.kWzByL div[direction='column']", state='visible', timeout=15000)
                        left_rows_elements = await page.query_selector_all("div.Box.Flex.cceZpO.kWzByL div[direction='column']")
                        seen_entries = set()
                        for row_element in left_rows_elements:
                            current_row_id = None
                            main_text_span = await row_element.query_selector("span")
                            if main_text_span:
                                text_from_span = (await main_text_span.inner_text()).strip()
                                if text_from_span and text_from_span.lower() not in ["all", "all teams", "eng"] and "united" not in text_from_span.lower() and "city" not in text_from_span.lower() and "fc" not in text_from_span.lower():
                                    current_row_id = text_from_span
                            nested_league_div = await row_element.query_selector("div.Text.beCNLk")
                            if nested_league_div and (await nested_league_div.is_visible()):
                                nested_league_text = (await nested_league_div.inner_text()).strip()
                                if nested_league_text and nested_league_text.lower() not in ["all", "all teams", "eng"]:
                                    current_row_id = nested_league_text
                            if current_row_id and current_row_id not in seen_entries:
                                season_keys_ordered.append(current_row_id)
                                seen_entries.add(current_row_id)

                        if not season_keys_ordered:
                            print(f"⚠️ Left column (season/league) info is empty or contains no valid entries: {league_text_to_select}. Skipping.")
                            continue

                        for tab_name, expected_headers in TAB_HEADERS.items():
                            try:
                                if tab_name != "General":
                                    await page.wait_for_selector(f"button:has-text('{tab_name}')", state='visible', timeout=7000)
                                    await page.click(f"button:has-text('{tab_name}')")
                                    await page.wait_for_load_state('networkidle', timeout=45000)
                                    await page.wait_for_timeout(700)

                                await page.wait_for_selector("div.Box.Flex.fEBZed.iWGVcA div[direction='column']", state='visible', timeout=15000)
                                right_rows = await page.query_selector_all("div.Box.Flex.fEBZed.iWGVcA div[direction='column']")
                                if not right_rows or len(right_rows) < 2:
                                    print(f"⚠️ Right column (stats) rows not found or are insufficient: League: {league_text_to_select}, Tab: {tab_name}. Skipping.")
                                    continue

                                for idx, right_row_element in enumerate(right_rows[1:]):
                                    if idx >= len(season_keys_ordered):
                                        print(f"❗ Left and right column row count mismatch. League: {league_text_to_select}, Tab: {tab_name}")
                                        break
                                    current_season_league_identifier = season_keys_ordered[idx]
                                    season_start_year = None
                                    year_match_for_season = re.search(r'(\d{2})/\d{2}', current_season_league_identifier)
                                    if year_match_for_season:
                                        season_start_year = 2000 + int(year_match_for_season.group(1))
                                    age_for_season = calculate_age_for_season(player_birth_year, season_start_year)
                                    values = []
                                    if tab_name == "General":
                                        spans = await right_row_element.query_selector_all("span")
                                        texts = [await span.inner_text() for span in spans if await span.inner_text()]
                                        values = [v.strip() if v.strip() != '-' else None for v in texts]
                                    elif tab_name == "Additional":
                                        cols = await right_row_element.query_selector_all("div[class*='Box Flex']")
                                        selected_indices = [0, 2, 3, 4]
                                        if len(cols) >= 5:
                                            last_five = cols[-5:]
                                            for i in selected_indices:
                                                if i < len(last_five):
                                                    col = last_five[i]
                                                    span = await col.query_selector("span")
                                                    val = await span.inner_text() if span else await col.inner_text()
                                                    values.append(val.strip() if val.strip() != '-' else None)
                                                else:
                                                    values.append(None)
                                        else:
                                            values = [None] * len(expected_headers)
                                    else:
                                        cols = await right_row_element.query_selector_all("div[class*='Box Flex']")
                                        for col in cols:
                                            span = await col.query_selector("span")
                                            val = await span.inner_text() if span else await col.inner_text()
                                            clean_val = val.strip() if val.strip() != "-" else None
                                            values.append(clean_val)

                                    values = values[-len(expected_headers):]
                                    values += [None for _ in range(len(expected_headers) - len(values))]
                                    row_data = dict(zip(expected_headers, values))
                                    key = (current_season_league_identifier, league_text_to_select, category_name)
                                    if key not in season_data:
                                        season_data[key] = {
                                            "Player": player_name,
                                            "Age": age_for_season,
                                            "Nationality": player_nationality,
                                            "Position": player_position,
                                            "Season": current_season_league_identifier,
                                            "League": league_text_to_select,
                                            "Category": category_name
                                        }
                                    for h, v in row_data.items():
                                        if h not in season_data[key]:
                                            season_data[key][h] = v
                                        else:
                                            if season_data[key][h] is None or season_data[key][h] == '-':
                                                season_data[key][h] = v
                            except Exception as e:
                                print(f"⚠️ Error fetching {tab_name} tab data ({league_text_to_select} - {category_name}): {e}")
                                continue
                except Exception as e:
                    print(f"❌ General error while getting or processing league list ({slug} - {category_name}): {e}")
                    continue

        except Exception as e:
            print(f"❌ Access to player page or general page error ({slug}): {e}")
        finally:
            await browser.close()
            print(f"Browser closed for: {slug}")
        
        return pd.DataFrame(season_data.values())

# 📁 Process player list
async def process_players_from_file(filepath: str):
    if not os.path.exists(filepath):
        print(f"Error: Player list file not found: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        slug_list = [line.strip() for line in f.readlines() if line.strip()]

    all_data = pd.DataFrame()
    for i, slug in enumerate(slug_list, 1):
        print(f"\n📦 {i}/{len(slug_list)} → {slug}")
        try:
            df = await get_sofascore_career(slug)
            if not df.empty:
                all_data = pd.concat([all_data, df], ignore_index=True)
            else:
                print(f"❗ No data could be fetched or an empty DataFrame was returned for {slug}.")
        except Exception as e:
            print(f"❌ Critical error during player processing ({slug}): {e}")

    os.makedirs("output", exist_ok=True)
    output_filename = "output/sofascore_all_league_players.csv"
    all_data.to_csv(output_filename, index=False, encoding="utf-8-sig")
    print(f"\n✅ All data saved to '{output_filename}' CSV file.")

# ▶️ Main entry point
if __name__ == "__main__":
    asyncio.run(process_players_from_file("output/premier_slug_list.txt"))
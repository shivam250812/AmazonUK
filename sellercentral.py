# sellercentral.py

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

try:
    import notifier
except ImportError:
    notifier = None

from playwright.async_api import async_playwright

# Shared Chrome profile setup
from chrome_profile import create_browser

# =========================================================
# CONFIG
# =========================================================

DEFAULT_INPUT_CSV = "input.csv"
DEFAULT_OUTPUT_CSV = "gated_output.csv"

SELLER_CENTRAL_URL = (
    "https://sellercentral.amazon.co.uk/product-search?ref_=myp_ps"
)

# =========================================================
# LOGIN CHECK
# =========================================================

async def ensure_logged_in(page):

    await page.goto(
        SELLER_CENTRAL_URL,
        timeout=90000,
        wait_until="domcontentloaded",
    )

    await asyncio.sleep(5)

    current_url = page.url.lower()

    if (
        "signin" in current_url
        or "ap/signin" in current_url
        or "ap/mfa" in current_url
    ):
        print(
            "\n  Seller Central not logged in or requiring MFA.\n"
            "   Please log in manually in the Chrome window.\n"
            "   Waiting up to 5 minutes for login...\n"
        )
        
        if notifier and notifier.is_configured():
            notifier.send_email(
                subject="ACTION REQUIRED: Seller Central MFA/Login",
                body="The Amazon Pipeline is paused because Seller Central requires login or an MFA code.\n\nPlease open the Chrome browser window that the script opened and complete the login/MFA process. The script will automatically resume once logged in (it will wait up to 5 minutes)."
            )

        # Wait up to 5 minutes, checking every 10 seconds
        for i in range(30):
            await asyncio.sleep(10)
            current_url = page.url.lower()
            if "signin" not in current_url and "ap/signin" not in current_url and "ap/mfa" not in current_url:
                break
        else:
            print(" Login timeout - Seller Central still on sign-in/MFA page.", file=sys.stderr)
            sys.exit(1)

    print(" Seller Central login active\n")


# =========================================================
# CHECK SINGLE ASIN
# =========================================================

async def check_asin(page, asin):

    print(f" Checking {asin}")

    try:

        # -------------------------------------------------
        # OPEN PRODUCT SEARCH PAGE
        # -------------------------------------------------

        await page.goto(
            SELLER_CENTRAL_URL,
            timeout=90000,
            wait_until="domcontentloaded",
        )

        await asyncio.sleep(5)

        # -------------------------------------------------
        # FIND SEARCH BOX
        # -------------------------------------------------

        search_box = page.locator(
            "input[placeholder*='product title']"
        ).first

        await search_box.wait_for(
            state="visible",
            timeout=30000
        )

        # -------------------------------------------------
        # CLEAR OLD TEXT
        # -------------------------------------------------

        await search_box.click()

        try:
            await search_box.press("Meta+A")
        except:
            await search_box.press("Control+A")

        await search_box.press("Backspace")

        # -------------------------------------------------
        # TYPE ASIN
        # -------------------------------------------------

        await search_box.fill(asin)

        await asyncio.sleep(1)

        # -------------------------------------------------
        # PRESS ENTER
        # -------------------------------------------------

        await search_box.press("Enter")

        # -------------------------------------------------
        # WAIT FOR PRODUCT PANEL
        # -------------------------------------------------

        panel = page.locator(
            "div[slot='header']"
        ).first

        await panel.wait_for(
            state="visible",
            timeout=30000
        )

        await asyncio.sleep(3)

        # -------------------------------------------------
        # SAVE SCREENSHOT
        # -------------------------------------------------

        os.makedirs("screenshots", exist_ok=True)

        await page.screenshot(
            path=f"screenshots/{asin}.png",
            full_page=True
        )

        # -------------------------------------------------
        # GET PAGE TEXT
        # -------------------------------------------------

        body_text = (
            await page.locator("body").inner_text()
        ).lower()

        button_texts = await page.locator(
            "button"
        ).all_inner_texts()

        buttons = " ".join(button_texts).lower()

        combined = body_text + "\n" + buttons

        # -------------------------------------------------
        # DETECT STATUS
        # -------------------------------------------------

        status = "UNKNOWN"
        message = ""

        # GATED
        if (
            "you need approval" in combined
            or "apply to sell" in combined
            or "request approval" in combined
        ):

            status = "GATED"
            message = "Brand approval required"

        # RESTRICTED
        elif (
            "listing limitation" in combined
            or "limitations apply" in combined
        ):

            status = "RESTRICTED"
            message = "Listing limitations apply"

        # NOT GATED
        elif (
            "sell this product" in combined
        ):

            status = "NOT_GATED"
            message = "Can sell"

        # PARTIAL
        elif (
            "copy listing" in combined
            and "sell this product" not in combined
        ):

            status = "PARTIAL_RESTRICTION"
            message = "Cannot directly sell"

        # -------------------------------------------------
        # EXTRACT TITLE
        # -------------------------------------------------

        title = ""

        try:

            title_locator = page.locator(
                "h4"
            ).first

            title = (
                await title_locator.inner_text()
            ).strip()

        except:
            pass

        print(f"   -> {status}")

        return {
            "asin": asin,
            "title": title,
            "status": status,
            "message": message,
        }

    except Exception as e:

        print(f" {asin}: {e}")

        return {
            "asin": asin,
            "title": "",
            "status": "ERROR",
            "message": str(e),
        }


# =========================================================
# PUBLIC API (for run_pipeline.py)
# =========================================================

def read_input_csv(input_csv: str) -> list[str]:
    asins = []
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = (
                row.get("ASIN")
                or row.get("asin")
                or row.get("Asin")
            )
            if asin:
                asins.append(asin.strip())
    return asins


async def run_seller_central(
    input_csv: str = DEFAULT_INPUT_CSV,
    output_csv: str = DEFAULT_OUTPUT_CSV,
) -> str:
    """
    Run Seller Central gating check for all ASINs in input_csv.
    Returns path to the output CSV.
    """
    asins = read_input_csv(input_csv)

    if not asins:
        print(f" No ASINs found in {input_csv}")
        return output_csv

    # Check/write header first
    header = ["ASIN", "TITLE", "STATUS", "MESSAGE"]
    file_exists = os.path.exists(output_csv) and os.path.getsize(output_csv) > 0
    has_header = False
    if file_exists:
        try:
            with open(output_csv, "r", encoding="utf-8") as f_check:
                first_line = f_check.readline()
                if "ASIN" in first_line and "STATUS" in first_line:
                    has_header = True
        except Exception:
            pass

    if not file_exists:
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
    elif not has_header:
        try:
            with open(output_csv, "r", encoding="utf-8") as f:
                content = f.read()
            with open(output_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                f.write(content)
        except Exception as e:
            print(f"Error prepending header to {output_csv}: {e}")

    # RESUME LOGIC: Check existing output_csv
    processed_asins = set()
    try:
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                asin = row.get("ASIN", "").strip()
                if asin:
                    processed_asins.add(asin)
    except Exception:
        pass

    asins_to_process = [a for a in asins if a not in processed_asins]

    if not asins_to_process:
        print(" All ASINs already processed. Nothing to do.")
        return output_csv

    if processed_asins:
        print(f" Resuming... {len(processed_asins)} already processed. {len(asins_to_process)} left to check.")

    async with async_playwright() as p:

        context = await create_browser(p, require_helium=False)

        page = await context.new_page()

        await ensure_logged_in(page)

        with open(
            output_csv,
            "a",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.writer(f)

            for asin in asins_to_process:

                result = await check_asin(
                    page,
                    asin
                )

                writer.writerow([
                    result["asin"],
                    result["title"],
                    result["status"],
                    result["message"],
                ])

                f.flush()

        print("\n Done")
        print(f" Output saved: {output_csv}")
        print(" Screenshots saved in screenshots/")

        await context.close()

    return output_csv


# =========================================================
# CLI ENTRY POINT
# =========================================================

def _parse_args():
    parser = argparse.ArgumentParser(description="Seller Central gating checker")
    parser.add_argument(
        "--input-csv",
        default=DEFAULT_INPUT_CSV,
        help=f"Input CSV with ASIN column (default: {DEFAULT_INPUT_CSV})",
    )
    parser.add_argument(
        "--output-csv",
        default=DEFAULT_OUTPUT_CSV,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT_CSV})",
    )
    return parser.parse_args()


async def main():
    args = _parse_args()
    await run_seller_central(args.input_csv, args.output_csv)


if __name__ == "__main__":
    asyncio.run(main())
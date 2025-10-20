I want to use this folder as a basis for a tool I can use to assess prices of used vehicles scraped from finn.no. This is primarily for personal use. I want the following:

- An "ad id fetcher" script
- A data downloader
- An analysis tool.

All scripts should have sensible defaults (which i may alter later), so that they can run without additional context.

The "ad id fetcher" script should take a base URL as input. This URL will point to a filtered list of vehicles that i have set up before-hand. There might be multiple pages, so the script will have to "navigate to next" unless the desired number of ids have already been fetched. Ids should be written to a separate table in a sql database. Take appropriate care if an id already exists in the table.

The data downloader fetches the id table from the database and pastes this ID into a pre-defined url. This should yield a valid finn.no ad which can be scraped for data. See scrape-articles for inspiration for this part. It should be possible to provide some filtering on which ads to scrape (time since last download or something like that, or just random).

The analysis tool should probably be either a nicegui or streamlit app for viewing and exploring the data. In particular, I am interested in styding a given brand and make, and analyzing cost vs. age and milage.

I suspect selenium would be required for scraping. For the database, I want to keep it simple, but I think a SQLite database (or similar) is better than using json? (Although i am open for suggestions).